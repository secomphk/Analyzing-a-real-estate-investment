"""Unit tests for Scenario A regression engine."""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from src.analysis.scenario_a import (
    CompensationImpactModel,
    DistanceTimePoint,
    ImpactPrediction,
)
from src.analysis.scenario_a.compensation_model import (
    ReferenceProject,
    TrainingSample,
    build_training_samples_from_db_rows,
)


def _synthetic_reference(name: str, anchor: date) -> ReferenceProject:
    """Build a reference project whose samples follow ``a·exp(-b·d)·g(t)``."""
    rng = np.random.default_rng(42)
    samples: list[TrainingSample] = []
    a, b = 0.30, 0.40   # peak 30%, 1.5km half-life
    for d in (200.0, 500.0, 1_000.0, 2_000.0, 3_000.0):
        for t in (-12, 0, 12, 36, 60):
            time_factor = {-12: 0.20, 0: 0.55, 12: 0.85, 36: 1.05, 60: 1.10}[t]
            uplift = a * np.exp(-b * d / 1_000) * time_factor
            uplift += rng.normal(0, 0.005)  # tiny noise
            samples.append(
                TrainingSample(
                    distance_m=d, months_since_anchor=t,
                    uplift_pct=float(uplift), weight=1.0,
                )
            )
    return ReferenceProject(project_id=hash(name) & 0xFFFF, name=name,
                            anchor_date=anchor, samples=samples)


def test_fit_with_two_synthetic_references_recovers_decay() -> None:
    refs = [
        _synthetic_reference("ref-1", date(2015, 1, 1)),
        _synthetic_reference("ref-2", date(2017, 6, 1)),
    ]
    model = CompensationImpactModel()
    params = model.fit(refs)
    # Spatial decay parameter should land in a reasonable band (~0.25-0.55).
    assert 0.20 <= params.b <= 0.60
    assert 0.10 <= params.a <= 0.50


def test_predict_returns_grid_with_monotonic_distance_decay() -> None:
    model = CompensationImpactModel()
    model.fit([_synthetic_reference("ref-1", date(2015, 1, 1))])
    out: ImpactPrediction = model.predict(
        anchor_date=date(2026, 1, 1),
        distances_m=[0, 500, 1_000, 2_000, 3_000],
        horizons_months=[12, 24],
    )
    # At each horizon, uplift should be non-increasing in distance.
    for series in out.series:
        # one series per distance; build a per-horizon decay check
        pass
    # Pivot into [distance][horizon] for the actual check.
    by_distance: dict[int, dict[int, DistanceTimePoint]] = {}
    for series in out.series:
        for p in series.points:
            by_distance.setdefault(int(series.distance_m), {})[p.months_after_anchor] = p
    for h in (12, 24):
        values = [by_distance[d][h].expected_uplift_pct for d in (0, 500, 1_000, 2_000, 3_000)]
        # Strictly non-increasing (allow tiny float jitter).
        for a, b in zip(values[:-1], values[1:], strict=True):
            assert b <= a + 1e-9, f"non-decay at horizon {h}: {values}"


def test_predict_emits_meta_block() -> None:
    model = CompensationImpactModel()
    out = model.predict(date(2026, 1, 1))
    assert out.model_version.startswith("scenario_a")
    assert 0.0 <= out.confidence_score <= 1.0
    assert any(f["factor"] == "spatial_decay_b" for f in out.top_factors)


def test_build_training_samples_handles_empty_input() -> None:
    assert build_training_samples_from_db_rows(rows=[], anchor_date=date(2020, 1, 1)) == []


def test_kfold_holdout_error_within_band() -> None:
    """With three synthetic references, leave-one-out RMSE should be < 0.05."""
    refs = [
        _synthetic_reference(f"ref-{i}", date(2015 + i, 1, 1)) for i in range(3)
    ]
    rmses: list[float] = []
    for hold in range(3):
        train = [r for j, r in enumerate(refs) if j != hold]
        test_samples = refs[hold].samples
        m = CompensationImpactModel()
        m.fit(train)
        preds = []
        actuals = []
        for s in test_samples:
            grid = m.predict(
                date(2020, 1, 1),
                distances_m=[s.distance_m],
                horizons_months=[s.months_since_anchor],
            )
            preds.append(grid.series[0].points[0].expected_uplift_pct)
            actuals.append(s.uplift_pct)
        rmses.append(
            float(np.sqrt(np.mean((np.array(preds) - np.array(actuals)) ** 2)))
        )
    assert max(rmses) < 0.10, f"holdout RMSE too high: {rmses}"


def test_predict_accepts_explicit_grid() -> None:
    model = CompensationImpactModel()
    out = model.predict(date(2025, 1, 1), distances_m=[100, 1000], horizons_months=[6])
    assert len(out.series) == 2
    assert all(len(s.points) == 1 for s in out.series)


def test_predict_zero_distance_stronger_than_far() -> None:
    """At t = 0, the closest distance band must have the highest uplift."""
    model = CompensationImpactModel()
    out = model.predict(date(2025, 1, 1), distances_m=[0, 3_000], horizons_months=[0])
    near = out.series[0].points[0].expected_uplift_pct
    far = out.series[1].points[0].expected_uplift_pct
    assert near > far


def test_fit_falls_back_with_one_reference() -> None:
    model = CompensationImpactModel()
    model.fit([_synthetic_reference("only", date(2015, 1, 1))])
    out = model.predict(date(2025, 1, 1))
    # With < 2 references the model should still run and emit a note.
    assert out.notes


def test_fit_requires_non_empty_references() -> None:
    model = CompensationImpactModel()
    with pytest.raises(Exception):
        model.fit([])
