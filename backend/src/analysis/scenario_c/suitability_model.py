"""DT/DI suitability classifier (XGBoost + SHAP).

Wraps an XGBoost binary classifier trained per ``store_type`` (DT vs DI).
The class is split into:

* :class:`SuitabilityModel` — pure model object. Stateless once fitted; safe
  to cache on ``app.state`` and call from FastAPI handlers.
* :class:`Suitability` / :class:`SuitabilityExplanation` — dataclasses
  returned to API callers (raw score, 0–100 normalised, top SHAP factors).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import numpy.typing as npt
import xgboost as xgb

from src.analysis.scenario_c.feature_engineering import FEATURE_NAMES, FeatureVector

DEFAULT_PARAMS: dict[str, Any] = {
    "n_estimators": 200,
    "max_depth": 4,
    "learning_rate": 0.05,
    "subsample": 0.85,
    "colsample_bytree": 0.85,
    "objective": "binary:logistic",
    "eval_metric": "auc",
    "tree_method": "hist",
}


# ─── DTOs ──────────────────────────────────────────────────────────────────


@dataclass(slots=True, frozen=True)
class Suitability:
    """The suitability prediction itself."""

    score_raw: float          # XGBoost output, 0–1
    score_100: int            # 0..100 (rounded)
    label: str                # "low" / "medium" / "high"
    target: str               # "DT" / "DI"
    model_version: str


@dataclass(slots=True)
class SuitabilityExplanation:
    """Top SHAP contributions for the predicted score."""

    top_factors: list[dict[str, Any]] = field(default_factory=list)
    confidence_score: float = 0.0


# ─── Model wrapper ─────────────────────────────────────────────────────────


class SuitabilityModel:
    """XGBoost-backed binary classifier with SHAP explanations.

    Two static targets are supported via ``target``: ``"DT"`` and ``"DI"``.
    The class is target-agnostic; the trainer instantiates one per target.
    """

    def __init__(
        self,
        *,
        target: str,
        model: xgb.XGBClassifier | None = None,
        feature_names: list[str] | None = None,
        model_version: str = "scenario_c_v1.0.0",
    ) -> None:
        if target not in ("DT", "DI"):
            raise ValueError(f"target must be 'DT' or 'DI', got {target!r}")
        self.target = target
        self.feature_names = feature_names or list(FEATURE_NAMES)
        self.model = model or xgb.XGBClassifier(**DEFAULT_PARAMS)
        self.model_version = model_version
        self._explainer: Any | None = None

    # ─── Persistence ────────────────────────────────────────────────────

    def save(self, directory: Path | str, *, version: str = "v1") -> Path:
        """Persist the wrapped object as ``suitability_<target>_<version>.pkl``."""
        out = Path(directory) / f"suitability_{self.target.lower()}_{version}.pkl"
        out.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "target": self.target,
                "feature_names": self.feature_names,
                "model_version": self.model_version,
                "model": self.model,
            },
            out,
        )
        return out

    @classmethod
    def load(cls, path: Path | str) -> SuitabilityModel:
        """Counterpart to :meth:`save`."""
        bundle = joblib.load(Path(path))
        return cls(
            target=bundle["target"],
            model=bundle["model"],
            feature_names=bundle["feature_names"],
            model_version=bundle.get("model_version", "scenario_c_v1.0.0"),
        )

    # ─── Training ───────────────────────────────────────────────────────

    def fit(
        self,
        X: npt.NDArray[np.float64],
        y: npt.NDArray[np.int64],
        *,
        sample_weight: npt.NDArray[np.float64] | None = None,
    ) -> None:
        """Train the classifier in-place. Forces float32 for XGBoost."""
        if X.shape[0] != y.shape[0]:
            raise ValueError(f"X and y disagree on n_samples: {X.shape[0]} vs {y.shape[0]}")
        if X.shape[1] != len(self.feature_names):
            raise ValueError(
                f"Expected {len(self.feature_names)} features, got {X.shape[1]}"
            )
        self.model.fit(X.astype(np.float32), y.astype(np.int32),
                       sample_weight=sample_weight)
        # Rebuild the SHAP explainer lazily on the next explain() call.
        self._explainer = None

    # ─── Inference ──────────────────────────────────────────────────────

    def predict(self, vec: FeatureVector | npt.NDArray[np.float64]) -> Suitability:
        """Return a :class:`Suitability` for one feature row."""
        arr = self._coerce(vec)
        proba = float(self.model.predict_proba(arr.reshape(1, -1))[0, 1])
        label = _bucket(proba)
        return Suitability(
            score_raw=round(proba, 4),
            score_100=round(proba * 100),
            label=label,
            target=self.target,
            model_version=self.model_version,
        )

    def predict_batch(
        self, vectors: list[FeatureVector] | npt.NDArray[np.float64]
    ) -> list[Suitability]:
        """Batched inference — keeps a single XGBoost call for ``predict_proba``."""
        if isinstance(vectors, np.ndarray):
            arr = vectors
        else:
            if not vectors:
                return []
            arr = np.vstack([v.to_array() for v in vectors])
        proba = self.model.predict_proba(arr.astype(np.float32))[:, 1]
        return [
            Suitability(
                score_raw=round(float(p), 4),
                score_100=round(float(p) * 100),
                label=_bucket(float(p)),
                target=self.target,
                model_version=self.model_version,
            )
            for p in proba
        ]

    # ─── Explanation ────────────────────────────────────────────────────

    def explain(
        self,
        vec: FeatureVector | npt.NDArray[np.float64],
        *,
        top_n: int = 3,
    ) -> SuitabilityExplanation:
        """Return the top-N SHAP contributors for ``vec``.

        Falls back to ``feature_importances_`` when SHAP raises (which can
        happen when the model has zero trained trees on tiny datasets).
        """
        arr = self._coerce(vec).reshape(1, -1).astype(np.float32)
        try:
            import shap  # noqa: PLC0415

            if self._explainer is None:
                self._explainer = shap.TreeExplainer(self.model)
            shap_values = self._explainer.shap_values(arr)
            shap_row = np.asarray(shap_values).reshape(-1)
            order = np.argsort(-np.abs(shap_row))[:top_n]
            factors = [
                {
                    "factor": self.feature_names[i],
                    "value": round(float(arr[0, i]), 4),
                    "shap": round(float(shap_row[i]), 4),
                    "impact": "positive" if shap_row[i] > 0 else "negative",
                }
                for i in order
            ]
            confidence = float(min(1.0, 0.4 + 0.6 * np.tanh(np.abs(shap_row).sum())))
            return SuitabilityExplanation(
                top_factors=factors,
                confidence_score=round(confidence, 3),
            )
        except Exception:  # noqa: BLE001 — SHAP is best-effort; fall back to importances
            importances = getattr(self.model, "feature_importances_", None)
            if importances is None:
                return SuitabilityExplanation(top_factors=[], confidence_score=0.5)
            order = np.argsort(-importances)[:top_n]
            factors = [
                {
                    "factor": self.feature_names[i],
                    "value": round(float(arr[0, i]), 4),
                    "shap": None,
                    "importance": round(float(importances[i]), 4),
                    "impact": "positive" if arr[0, i] >= 0 else "neutral",
                }
                for i in order
            ]
            return SuitabilityExplanation(top_factors=factors, confidence_score=0.5)

    # ─── Internal ───────────────────────────────────────────────────────

    def _coerce(
        self, vec: FeatureVector | npt.NDArray[np.float64]
    ) -> npt.NDArray[np.float64]:
        if isinstance(vec, np.ndarray):
            return vec
        return vec.to_array()


def _bucket(p: float) -> str:
    if p >= 0.66:
        return "high"
    if p >= 0.33:
        return "medium"
    return "low"
