"""Unit tests for the cross-scenario similarity matcher."""

from __future__ import annotations

import numpy as np
import pytest

from src.analysis.similarity import SimilarityMatcher


FEATURES = ["road_progress", "population_avg", "aadt_avg"]


def test_similarity_perfect_match_returns_one() -> None:
    m = SimilarityMatcher(FEATURES, weights={
        "road_progress": 0.30, "population_avg": 0.40, "aadt_avg": 0.30,
    })
    a = np.array([0.5, 30_000.0, 12_000.0])
    assert m.similarity(a, a) == pytest.approx(1.0, rel=1e-6)


def test_similarity_orthogonal_returns_zero() -> None:
    m = SimilarityMatcher(FEATURES)
    a = np.array([1.0, 0.0, 0.0])
    b = np.array([0.0, 1.0, 0.0])
    assert m.similarity(a, b) == pytest.approx(0.0, abs=1e-6)


def test_similarity_topk_orders_by_score() -> None:
    m = SimilarityMatcher(FEATURES, weights={
        "road_progress": 0.30, "population_avg": 0.40, "aadt_avg": 0.30,
    })
    query = np.array([0.5, 30_000.0, 12_000.0])
    candidates = np.array(
        [
            [0.5, 30_000.0, 12_000.0],   # identical → top
            [0.1, 15_000.0,  4_000.0],
            [0.5, 30_500.0, 12_300.0],   # near-match
        ]
    )
    out = m.topk(query, candidates, k=3)
    assert out[0][0] == 0
    assert out[1][0] == 2
    assert out[2][0] == 1


def test_weights_normalize_to_sum_one() -> None:
    m = SimilarityMatcher(FEATURES, weights={
        "road_progress": 1.0, "population_avg": 1.0, "aadt_avg": 1.0,
    })
    assert sum(m.weights.values()) == pytest.approx(1.0)
