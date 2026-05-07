"""Unit tests for Scenario C — pure-Python pieces (model + index + rules)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pytest

from src.analysis.scenario_c.feature_engineering import FEATURE_NAMES, FeatureVector
from src.analysis.scenario_c.rationale_generator import (
    RationaleCategory,
    RationaleGenerator,
    RationaleImpact,
)
from src.analysis.scenario_c.similarity_search import StoreSimilarityIndex
from src.analysis.scenario_c.suitability_model import SuitabilityModel


# ─── FeatureVector ──────────────────────────────────────────────────────────


def test_feature_vector_to_array_uses_feature_names_order() -> None:
    vec = FeatureVector(
        pnu="0" * 19, snapshot_date=date(2024, 1, 1),
        values={"land_area_m2": 500.0, "population_within_1km": 12_000.0},
    )
    arr = vec.to_array()
    assert arr.shape == (len(FEATURE_NAMES),)
    idx = FEATURE_NAMES.index("land_area_m2")
    assert arr[idx] == 500.0


# ─── SuitabilityModel ──────────────────────────────────────────────────────


def _toy_dataset(n: int = 64) -> tuple[np.ndarray, np.ndarray]:
    """Build a separable dataset where higher feature values ⇒ positive class."""
    rng = np.random.default_rng(0)
    n_features = len(FEATURE_NAMES)
    X = rng.normal(size=(n, n_features)).astype(np.float64)
    # Force linear separability on the first two features.
    y = ((X[:, 0] + X[:, 1]) > 0).astype(np.int64)
    # Bias the positive class' first features upward.
    X[y == 1, 0] += 1.5
    X[y == 1, 1] += 1.0
    return X, y


def test_suitability_model_fits_and_predicts() -> None:
    X, y = _toy_dataset()
    model = SuitabilityModel(target="DT")
    model.fit(X, y)

    pos = X[y == 1].mean(axis=0)
    neg = X[y == 0].mean(axis=0)
    score_pos = model.predict(pos.astype(np.float64))
    score_neg = model.predict(neg.astype(np.float64))
    # Mean positive sample should score higher than mean negative.
    assert score_pos.score_raw > score_neg.score_raw
    assert score_pos.label in {"low", "medium", "high"}
    assert 0 <= score_pos.score_100 <= 100


def test_suitability_save_and_load_round_trip(tmp_path: Path) -> None:
    X, y = _toy_dataset()
    model = SuitabilityModel(target="DI")
    model.fit(X, y)
    saved = model.save(tmp_path, version="vtest")

    reloaded = SuitabilityModel.load(saved)
    assert reloaded.target == "DI"
    assert reloaded.feature_names == FEATURE_NAMES
    # Same input → same prediction.
    pred1 = model.predict(X[0])
    pred2 = reloaded.predict(X[0])
    assert pred1.score_raw == pytest.approx(pred2.score_raw, rel=1e-4)


def test_suitability_explain_returns_top_factors() -> None:
    X, y = _toy_dataset(n=80)
    model = SuitabilityModel(target="DT")
    model.fit(X, y)
    explanation = model.explain(X[0], top_n=3)
    assert 1 <= len(explanation.top_factors) <= 3
    assert 0.0 <= explanation.confidence_score <= 1.0


def test_predict_batch_matches_per_row() -> None:
    X, y = _toy_dataset()
    model = SuitabilityModel(target="DT")
    model.fit(X, y)
    batch = model.predict_batch(X[:5].astype(np.float64))
    per_row = [model.predict(X[i]) for i in range(5)]
    assert [b.score_100 for b in batch] == [p.score_100 for p in per_row]


# ─── FAISS index ───────────────────────────────────────────────────────────


def test_similarity_index_round_trip(tmp_path: Path) -> None:
    rng = np.random.default_rng(0)
    n_features = len(FEATURE_NAMES)
    vectors = rng.normal(size=(20, n_features)).astype(np.float32)
    store_ids = list(range(101, 121))
    idx = StoreSimilarityIndex.build(store_ids=store_ids, vectors=vectors)

    saved = idx.save(tmp_path)
    assert saved.exists()
    reloaded = StoreSimilarityIndex.load(tmp_path, version="v1")
    assert reloaded.store_ids == store_ids
    assert reloaded.dimension == n_features


def test_similarity_search_excludes_self() -> None:
    rng = np.random.default_rng(0)
    n_features = len(FEATURE_NAMES)
    vectors = rng.normal(size=(10, n_features)).astype(np.float32)
    idx = StoreSimilarityIndex.build(store_ids=list(range(10)), vectors=vectors)
    query = vectors[3]
    out = idx.search(query, top_n=5, exclude_store_id=3)
    assert all(r.store_id != 3 for r in out)


def test_similarity_search_returns_self_when_not_excluded() -> None:
    n_features = len(FEATURE_NAMES)
    vectors = np.eye(5, n_features, dtype=np.float32)
    idx = StoreSimilarityIndex.build(store_ids=[10, 20, 30, 40, 50], vectors=vectors)
    out = idx.search(vectors[0], top_n=1)
    assert out[0].store_id == 10
    assert out[0].score == pytest.approx(1.0, rel=1e-3)


def test_similarity_build_rejects_empty() -> None:
    with pytest.raises(ValueError, match="zero vectors"):
        StoreSimilarityIndex.build(store_ids=[], vectors=np.empty((0, 4), dtype=np.float32))


# ─── RationaleGenerator ────────────────────────────────────────────────────


def test_rationale_generator_emits_categorised_bullets() -> None:
    vec = FeatureVector(
        pnu=None, snapshot_date=date(2024, 1, 1),
        values={
            "land_area_m2": 1_800,
            "land_price_5y_growth": 0.40,
            "population_within_3km": 60_000,
            "competitor_count_within_500m": 0,
            "aadt_nearest_road": 18_000,
            "distance_to_nearest_road_m": 30,
            "nearby_road_expansion": 1,
            "population_growth_3y_pct": 0.07,
        },
    )
    rationales = RationaleGenerator().generate(vec)
    categories = {r.category for r in rationales}
    assert RationaleCategory.PROPERTY in categories
    assert RationaleCategory.SURROUNDINGS in categories
    assert RationaleCategory.TRAFFIC in categories
    assert RationaleCategory.CATALYST in categories
    # All clearly-positive signals → positive impact dominates.
    pos = sum(1 for r in rationales if r.impact == RationaleImpact.POSITIVE)
    neg = sum(1 for r in rationales if r.impact == RationaleImpact.NEGATIVE)
    assert pos > neg


def test_rationale_negative_signals_surface() -> None:
    vec = FeatureVector(
        pnu=None, snapshot_date=date(2024, 1, 1),
        values={
            "land_area_m2": 200,
            "population_within_3km": 5_000,
            "competitor_count_within_500m": 6,
            "aadt_nearest_road": 1_200,
            "distance_to_nearest_road_m": 800,
            "population_growth_3y_pct": -0.05,
        },
    )
    rationales = RationaleGenerator().generate(vec)
    assert any(r.impact == RationaleImpact.NEGATIVE for r in rationales)
