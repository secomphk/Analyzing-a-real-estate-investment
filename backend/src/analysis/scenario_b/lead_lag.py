"""Lead-lag analysis between two monthly time-series.

Computes cross-correlation across ±24 months and classifies the optimal
lag into ``leading`` / ``coincident`` / ``lagging`` per the spec
(thresholds at ±3 months).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

import numpy as np


class LeadLagClassification(str, Enum):
    """Relationship of A relative to B at the best lag."""

    LEADING = "leading"          # A leads B (lag < -3)
    COINCIDENT = "coincident"    # |lag| ≤ 3
    LAGGING = "lagging"          # A lags B (lag > +3)
    UNCERTAIN = "uncertain"      # Insufficient data / weak signal


@dataclass(slots=True)
class LeadLagAnalysis:
    """Per-pair lead-lag result."""

    a: str
    b: str
    best_lag_months: int
    best_correlation: float
    classification: LeadLagClassification
    series_correlations: list[tuple[int, float]]


class LeadLagClassifier:
    """Cross-correlation classifier with the spec's ±3-month thresholds."""

    def __init__(
        self,
        *,
        max_lag_months: int = 24,
        coincident_threshold_months: int = 3,
        signal_threshold: float = 0.35,
    ) -> None:
        self._max_lag = max_lag_months
        self._coincident = coincident_threshold_months
        self._signal_threshold = signal_threshold

    def analyze(
        self,
        *,
        a: str,
        b: str,
        series_a: Sequence[float],
        series_b: Sequence[float],
    ) -> LeadLagAnalysis:
        """Return the lag at which ``a`` and ``b`` correlate most strongly.

        Sign convention: ``best_lag_months < 0`` means ``a`` leads ``b``
        (per the Scenario B spec). Internally we compute
        ``corr(a[t], b[t + k])`` and report ``-k`` so the output uses the
        natural "a precedes b → negative" convention.
        """
        arr_a = np.asarray(series_a, dtype=np.float64)
        arr_b = np.asarray(series_b, dtype=np.float64)
        if arr_a.size != arr_b.size:
            raise ValueError("Series must be the same length.")

        sa = _standardize(arr_a)
        sb = _standardize(arr_b)

        max_lag = min(self._max_lag, arr_a.size - 1)
        correlations_raw: list[tuple[int, float]] = []
        best_internal_lag = 0
        best_corr = 0.0

        for lag in range(-max_lag, max_lag + 1):
            corr = _shifted_corr(sa, sb, lag)
            # Report the user-facing lag with flipped sign so that "a leads b"
            # corresponds to a *negative* lag in the API/UI.
            correlations_raw.append((-lag, round(float(corr), 4)))
            if abs(corr) > abs(best_corr):
                best_corr = float(corr)
                best_internal_lag = lag

        reported_lag = -best_internal_lag

        if abs(best_corr) < self._signal_threshold:
            classification = LeadLagClassification.UNCERTAIN
        elif reported_lag < -self._coincident:
            classification = LeadLagClassification.LEADING
        elif reported_lag > self._coincident:
            classification = LeadLagClassification.LAGGING
        else:
            classification = LeadLagClassification.COINCIDENT

        # Sort by lag ascending so plotting is straightforward.
        correlations_raw.sort(key=lambda t: t[0])

        return LeadLagAnalysis(
            a=a,
            b=b,
            best_lag_months=int(reported_lag),
            best_correlation=round(best_corr, 4),
            classification=classification,
            series_correlations=correlations_raw,
        )


# ─── Internal helpers ──────────────────────────────────────────────────────


def _standardize(arr: np.ndarray) -> np.ndarray:
    if arr.size == 0:
        return arr
    std = arr.std()
    if std < 1e-12:
        return np.zeros_like(arr)
    out: np.ndarray = (arr - arr.mean()) / std
    return out


def _shifted_corr(a: np.ndarray, b: np.ndarray, lag: int) -> float:
    """Pearson ``corr(a[t], b[t + lag])`` over the overlapping window.

    The full-series standardization done by the caller doesn't guarantee
    that an arbitrary slice has mean 0 / std 1, so we recompute correlation
    on the slice itself with ``np.corrcoef``.
    """
    if lag == 0:
        a_w, b_w = a, b
    elif lag > 0:
        a_w, b_w = a[:-lag], b[lag:]
    else:  # lag < 0
        a_w, b_w = a[-lag:], b[:lag]
    if a_w.size < 3:
        return 0.0
    if a_w.std() < 1e-12 or b_w.std() < 1e-12:
        return 0.0
    with np.errstate(invalid="ignore"):
        c = np.corrcoef(a_w, b_w)[0, 1]
    return float(0.0 if np.isnan(c) else c)
