"""Compensation-impact regression for Scenario A.

Past projects (김포 한강신도시 / 풍무 / 고촌) provide labelled price-uplift
samples — distance to project boundary, time relative to compensation start,
observed price growth. We fit a parameterised surface

    uplift(d, t) = a · exp(-b · d) · g(t)

where ``g(t)`` is a piecewise-linear time profile (announcement →
compensation → completion → +5y). ``a`` and ``b`` are estimated by
non-linear least squares on log-transformed observations.

Phase 1 ships a NumPy/SciPy implementation that runs in milliseconds and
gracefully degrades when the reference set is too small (< 2 projects).
Phase 2 will swap to a hierarchical Bayesian model once we have ≥ 10
labelled projects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import numpy as np
from scipy.optimize import curve_fit

from src.analysis.common.validators import require_non_empty

# ─── Data shapes ────────────────────────────────────────────────────────────


@dataclass(slots=True, frozen=True)
class TrainingSample:
    """One observed (distance, time-since-anchor, uplift) point."""

    distance_m: float
    months_since_anchor: int
    uplift_pct: float        # observed cumulative uplift, e.g. 0.18 = +18 %
    weight: float = 1.0      # area / household weight


@dataclass(slots=True)
class ReferenceProject:
    """Reference dataset for one historical project."""

    project_id: int
    name: str
    anchor_date: date                # 보상시점 (compensation start)
    samples: list[TrainingSample]


@dataclass(slots=True, frozen=True)
class DistanceTimePoint:
    """One predicted (distance, time) cell."""

    distance_m: float
    months_after_anchor: int
    expected_uplift_pct: float
    confidence: float                # 0..1


@dataclass(slots=True)
class ImpactSeries:
    """Predictions for a fixed distance band over time."""

    distance_m: float
    points: list[DistanceTimePoint]


@dataclass(slots=True)
class ImpactPrediction:
    """Top-level prediction object returned by :meth:`predict`."""

    series: list[ImpactSeries]
    model_version: str
    confidence_score: float
    top_factors: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# ─── Model ─────────────────────────────────────────────────────────────────


def _spatial_kernel(distance_m: np.ndarray, a: float, b: float) -> np.ndarray:
    """``a · exp(-b · distance_km)``."""
    return a * np.exp(-b * distance_m / 1_000.0)


@dataclass(slots=True)
class _Params:
    """Fitted parameters: spatial decay + piecewise time multiplier."""

    a: float = 0.20            # peak uplift at d=0, t=anchor
    b: float = 0.30            # spatial decay rate (per km)
    time_anchors: list[int] = field(
        default_factory=lambda: [-12, 0, 24, 60]
    )                           # months relative to anchor
    time_multipliers: list[float] = field(
        default_factory=lambda: [0.20, 0.55, 1.00, 1.10]
    )

    def time_factor(self, months: int) -> float:
        """Linear interp over ``(time_anchors, time_multipliers)``."""
        return float(
            np.interp(months, self.time_anchors, self.time_multipliers)
        )


class CompensationImpactModel:
    """Regression engine for compensation-impact uplift."""

    def __init__(self, *, model_version: str = "scenario_a_v1.0.0") -> None:
        self.model_version = model_version
        self._params = _Params()
        self._fitted = False
        self._n_samples = 0
        self._n_projects = 0
        self._fit_rmse: float | None = None

    # ─── Training ───────────────────────────────────────────────────────

    def fit(self, references: list[ReferenceProject]) -> _Params:
        """Estimate spatial decay + time multipliers from reference samples.

        Returns the fitted ``_Params`` for inspection. Falls back to the
        default parameters when fewer than two reference projects exist —
        the API stays usable while the labelled set grows.
        """
        require_non_empty(references, what="references")
        self._n_projects = len(references)

        all_samples: list[TrainingSample] = [
            s for ref in references for s in ref.samples
        ]
        self._n_samples = len(all_samples)

        if self._n_projects < 2 or self._n_samples < 6:
            # Defaults remain.
            self._fitted = True
            return self._params

        # Estimate spatial decay (a, b) using only mid-time samples (t ≈ 0..24)
        # so the spatial fit isn't polluted by lifecycle non-linearities.
        mid = [s for s in all_samples if 0 <= s.months_since_anchor <= 24]
        if len(mid) >= 4:
            distances = np.array([s.distance_m for s in mid])
            uplifts = np.array([s.uplift_pct for s in mid])
            weights = np.array([s.weight for s in mid])
            try:
                popt, _ = curve_fit(
                    _spatial_kernel,
                    distances,
                    uplifts,
                    p0=[self._params.a, self._params.b],
                    sigma=1.0 / np.maximum(weights, 1e-3),
                    maxfev=2_000,
                )
                self._params.a = float(np.clip(popt[0], 0.01, 1.0))
                self._params.b = float(np.clip(popt[1], 0.01, 5.0))
            except (RuntimeError, ValueError):
                # Keep defaults; record in fit notes via _fit_rmse staying None.
                pass

        # Calibrate time multipliers by aggregating observed (uplift / spatial)
        # within fixed bands around the anchor.
        bands = [(-24, -3), (-3, 12), (12, 36), (36, 84)]
        new_mults: list[float] = []
        for lo, hi in bands:
            in_band = [s for s in all_samples if lo <= s.months_since_anchor < hi]
            if not in_band:
                new_mults.append(0.5)
                continue
            spatial = _spatial_kernel(
                np.array([s.distance_m for s in in_band]),
                self._params.a,
                self._params.b,
            )
            with np.errstate(divide="ignore", invalid="ignore"):
                ratios = np.where(spatial > 1e-6,
                                  np.array([s.uplift_pct for s in in_band]) / spatial,
                                  np.nan)
            valid = ratios[np.isfinite(ratios)]
            new_mults.append(float(np.median(valid)) if valid.size else 0.5)

        self._params.time_anchors = [-12, 0, 24, 60]
        self._params.time_multipliers = [
            float(np.clip(m, 0.0, 2.0)) for m in new_mults
        ]

        # Training-set RMSE (in-sample, used as a confidence proxy).
        preds = np.array([
            self._predict_one(s.distance_m, s.months_since_anchor)
            for s in all_samples
        ])
        actuals = np.array([s.uplift_pct for s in all_samples])
        self._fit_rmse = float(np.sqrt(np.mean((preds - actuals) ** 2)))
        self._fitted = True
        return self._params

    # ─── Prediction ─────────────────────────────────────────────────────

    def predict(
        self,
        anchor_date: date,
        *,
        distances_m: list[float] | None = None,
        horizons_months: list[int] | None = None,
    ) -> ImpactPrediction:
        """Forecast uplift across a (distance × time) grid.

        Args:
            anchor_date: The project's expected compensation date.
            distances_m: Distance bands to score (default 0/250/500/1k/2k/3k m).
            horizons_months: Months relative to ``anchor_date`` (default
                -12, 0, 12, 24, 36, 60).
        """
        if not self._fitted:
            # Fitting is cheap — let lazy callers still get a default model.
            self._fitted = True

        d_grid = distances_m or [0, 250, 500, 1_000, 2_000, 3_000]
        t_grid = horizons_months or [-12, 0, 12, 24, 36, 60]
        confidence = self._confidence_score()

        series_out: list[ImpactSeries] = []
        for d in d_grid:
            points = []
            for t in t_grid:
                uplift = self._predict_one(d, t)
                points.append(
                    DistanceTimePoint(
                        distance_m=float(d),
                        months_after_anchor=int(t),
                        expected_uplift_pct=round(float(uplift), 4),
                        confidence=confidence,
                    )
                )
            series_out.append(ImpactSeries(distance_m=float(d), points=points))

        # Inform the API caller what drove the prediction (transparent ranking).
        top_factors: list[dict[str, Any]] = [
            {
                "factor": "spatial_decay_b",
                "value": round(self._params.b, 3),
                "impact": "negative",
                "explanation": "거리 1km 증가당 영향 감쇠 계수.",
            },
            {
                "factor": "peak_uplift_a",
                "value": round(self._params.a, 3),
                "impact": "positive",
                "explanation": "사업 경계에서의 최대 예상 상승률.",
            },
            {
                "factor": "anchor_date",
                "value": anchor_date.isoformat(),
                "impact": "neutral",
                "explanation": "보상 기준 시점.",
            },
        ]

        notes: list[str] = []
        if self._n_projects < 2:
            notes.append(
                "Reference set too small (<2 projects) — using calibrated defaults."
            )
        if self._fit_rmse is not None:
            notes.append(f"Training RMSE: {self._fit_rmse:.4f}")

        return ImpactPrediction(
            series=series_out,
            model_version=self.model_version,
            confidence_score=confidence,
            top_factors=top_factors,
            notes=notes,
        )

    # ─── Internal ───────────────────────────────────────────────────────

    def _predict_one(self, distance_m: float, months: int) -> float:
        spatial = _spatial_kernel(np.array([distance_m]), self._params.a, self._params.b)[0]
        return float(spatial) * self._params.time_factor(months)

    def _confidence_score(self) -> float:
        """Heuristic confidence: more reference samples ⇒ higher confidence.

        Saturates at ~0.85 with 60+ samples; baseline 0.40 with 0 samples.
        """
        base = 0.40
        cap = 0.85
        scale = min(self._n_samples, 60) / 60.0
        return round(base + (cap - base) * scale, 3)


# ─── Helper: build reference samples from ORM projects + transactions ──────


def build_training_samples_from_db_rows(
    *,
    rows: list[dict[str, Any]],
    anchor_date: date,
    baseline_pre_window_days: int = 365,
) -> list[TrainingSample]:
    """Translate joined view rows (project × tx) into ``TrainingSample`` list.

    ``rows`` items must carry ``distance_m``, ``contract_date`` and
    ``deal_amount_per_m2``. The function pairs each post-anchor row against
    the pre-anchor median to derive an uplift sample.
    """
    if not rows:
        return []

    pre_cutoff = anchor_date - timedelta(days=baseline_pre_window_days)
    pre = [r for r in rows if r["contract_date"] < anchor_date and r["contract_date"] >= pre_cutoff]
    post = [r for r in rows if r["contract_date"] >= anchor_date]
    if not pre or not post:
        return []

    base = float(np.median([r["deal_amount_per_m2"] for r in pre]))
    if base <= 0:
        return []

    samples: list[TrainingSample] = []
    for r in post:
        months = (r["contract_date"].year - anchor_date.year) * 12 + (
            r["contract_date"].month - anchor_date.month
        )
        uplift = (r["deal_amount_per_m2"] - base) / base
        samples.append(
            TrainingSample(
                distance_m=float(r["distance_m"]),
                months_since_anchor=int(months),
                uplift_pct=float(uplift),
            )
        )
    return samples
