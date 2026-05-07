"""Unit tests for Scenario B correlation + lead-lag classifier."""

from __future__ import annotations

import math

import numpy as np
import pytest

from src.analysis.scenario_b.correlation import pearson_matrix
from src.analysis.scenario_b.lead_lag import (
    LeadLagClassification,
    LeadLagClassifier,
)
from src.analysis.scenario_b.three_variable import _interpolate, _progress_for_month
from datetime import date


def test_pearson_perfect_positive_correlation() -> None:
    series = {"a": [1.0, 2.0, 3.0, 4.0, 5.0],
              "b": [2.0, 4.0, 6.0, 8.0, 10.0]}
    out = pearson_matrix(series)
    assert math.isclose(out.get("a", "b"), 1.0, rel_tol=1e-3)


def test_pearson_perfect_negative_correlation() -> None:
    series = {"a": [1.0, 2.0, 3.0], "b": [3.0, 2.0, 1.0]}
    out = pearson_matrix(series)
    assert math.isclose(out.get("a", "b"), -1.0, rel_tol=1e-3)


def test_pearson_short_series_returns_identity_diagonal() -> None:
    out = pearson_matrix({"a": [1.0], "b": [1.0]})
    assert out.get("a", "a") == 1.0
    assert out.get("a", "b") == 0.0


def test_lead_lag_detects_a_leading() -> None:
    """If A leads B by 5 months, ``best_lag_months`` should be ~ -5.

    Random-walk signal so the correlation surface has a single peak —
    a periodic signal would tie at multiple lags.
    """
    rng = np.random.default_rng(7)
    a = rng.normal(size=120).cumsum()
    b = np.empty_like(a)
    b[:5] = a[:5]
    b[5:] = a[:-5] + rng.normal(size=len(a) - 5) * 0.05
    out = LeadLagClassifier().analyze(
        a="a", b="b", series_a=a.tolist(), series_b=b.tolist()
    )
    assert out.classification == LeadLagClassification.LEADING
    assert -8 <= out.best_lag_months <= -3


def test_lead_lag_detects_coincident() -> None:
    rng = np.random.default_rng(1)
    a = rng.normal(size=60).cumsum()
    b = a + rng.normal(size=60) * 0.1
    out = LeadLagClassifier().analyze(a="a", b="b", series_a=a.tolist(), series_b=b.tolist())
    assert out.classification in {LeadLagClassification.COINCIDENT, LeadLagClassification.UNCERTAIN}


def test_lead_lag_uncertain_when_no_signal() -> None:
    """Long pure-noise series → max abs correlation should fall below 0.35."""
    rng = np.random.default_rng(2)
    a = rng.normal(size=400)
    b = rng.normal(size=400)
    out = LeadLagClassifier().analyze(a="a", b="b", series_a=a.tolist(), series_b=b.tolist())
    assert out.classification == LeadLagClassification.UNCERTAIN


def test_progress_steps_through_stages() -> None:
    stages = [
        (date(2018, 1, 1), "planned"),
        (date(2020, 1, 1), "under_construction"),
        (date(2022, 6, 1), "completed"),
    ]
    assert _progress_for_month(stages, date(2017, 1, 1)) == 0.0
    assert _progress_for_month(stages, date(2019, 1, 1)) == 0.10
    assert _progress_for_month(stages, date(2021, 1, 1)) == 0.60
    assert _progress_for_month(stages, date(2023, 1, 1)) == 1.0


def test_interpolate_fills_internal_nans() -> None:
    result = _interpolate([1.0, float("nan"), float("nan"), 4.0])
    assert result == pytest.approx([1.0, 2.0, 3.0, 4.0])


def test_interpolate_forward_fills_leading() -> None:
    result = _interpolate([float("nan"), float("nan"), 5.0, 7.0])
    assert result[0] == 5.0
    assert result[1] == 5.0
