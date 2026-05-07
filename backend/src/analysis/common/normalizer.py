"""Numeric normalization helpers used by every scenario.

Tiny pure functions — no DB, no I/O — so they can be the building blocks
in feature pipelines and tests without setup.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import numpy.typing as npt


def minmax_scale(values: Sequence[float]) -> npt.NDArray[np.float64]:
    """Scale ``values`` to [0, 1]. All-equal arrays return zeros."""
    arr: npt.NDArray[np.float64] = np.asarray(values, dtype=np.float64)
    if arr.size == 0:
        return arr
    lo, hi = arr.min(), arr.max()
    if hi - lo < 1e-12:
        return np.zeros_like(arr)
    out: npt.NDArray[np.float64] = (arr - lo) / (hi - lo)
    return out


def standardize(values: Sequence[float]) -> npt.NDArray[np.float64]:
    """Zero-mean, unit-variance scaling. Constant arrays return zeros."""
    arr: npt.NDArray[np.float64] = np.asarray(values, dtype=np.float64)
    if arr.size == 0:
        return arr
    std = arr.std()
    if std < 1e-12:
        return np.zeros_like(arr)
    out: npt.NDArray[np.float64] = (arr - arr.mean()) / std
    return out


def zscore_clip(
    values: Sequence[float], *, clip: float = 3.0
) -> npt.NDArray[np.float64]:
    """Standardize then clamp to ``[-clip, +clip]`` — robust to outliers."""
    return np.clip(standardize(values), -clip, clip)


def safe_pct_change(current: float, previous: float | None) -> float | None:
    """Return ``(current - previous) / previous`` as a fraction, or ``None``.

    ``None`` is returned for missing or zero-divisor cases so callers don't
    have to special-case the first observation.
    """
    if previous is None or previous == 0:
        return None
    return (current - previous) / previous
