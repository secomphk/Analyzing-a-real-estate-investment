"""Unit tests for the cross-scenario helpers."""

from __future__ import annotations

import math
from datetime import date

import numpy as np
import pytest

from src.analysis.common import (
    AnalysisInputError,
    minmax_scale,
    require_non_empty,
    safe_pct_change,
    standardize,
    validate_coordinate,
    validate_date_range,
    validate_pnu,
    zscore_clip,
)


def test_minmax_scale_zero_range_returns_zeros() -> None:
    np.testing.assert_array_equal(minmax_scale([5, 5, 5]), np.array([0, 0, 0]))


def test_standardize_unit_variance() -> None:
    out = standardize([1, 2, 3, 4, 5])
    assert math.isclose(out.std(), 1.0, rel_tol=1e-6)


def test_zscore_clip_clamps_outliers() -> None:
    out = zscore_clip([0, 1, 2, 100], clip=2.0)
    assert out.max() <= 2.0
    assert out.min() >= -2.0


def test_safe_pct_change_returns_none_on_zero() -> None:
    assert safe_pct_change(10, 0) is None
    assert safe_pct_change(10, None) is None
    assert safe_pct_change(110, 100) == pytest.approx(0.10)


def test_validate_pnu_strips_hyphens() -> None:
    assert validate_pnu("1234567890-1-0001-0000") == "1234567890100010000"
    with pytest.raises(AnalysisInputError):
        validate_pnu("12345")


def test_validate_coordinate_rejects_swapped_axes() -> None:
    with pytest.raises(AnalysisInputError):
        validate_coordinate(127.0, 37.0)  # swapped


def test_validate_date_range() -> None:
    validate_date_range(date(2024, 1, 1), date(2024, 12, 31))
    with pytest.raises(AnalysisInputError):
        validate_date_range(date(2024, 12, 31), date(2024, 1, 1))


def test_require_non_empty() -> None:
    with pytest.raises(AnalysisInputError):
        require_non_empty([], what="things")
    require_non_empty([1], what="things")
