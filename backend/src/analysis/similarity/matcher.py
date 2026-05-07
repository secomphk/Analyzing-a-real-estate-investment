"""Weighted cosine-similarity matcher.

Phase 1 picks the per-feature weights via a static map (the spec gives
``road_progress=0.30, population=0.40, traffic=0.30`` for Scenario B).
Phase 2 will accept SHAP-derived weights from the suitability model.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

import numpy as np
import numpy.typing as npt

# Default Scenario B weights per the spec.
DEFAULT_REGION_WEIGHTS: dict[str, float] = {
    "road_progress": 0.30,
    "population_avg": 0.20,
    "population_growth_3y": 0.20,
    "aadt_avg": 0.15,
    "aadt_growth_3y": 0.15,
}


@dataclass(slots=True, frozen=True)
class SimilarityWeight:
    """Convenience wrapper. Auto-normalises so weights sum to 1.0."""

    weights: Mapping[str, float]

    def normalised(self) -> dict[str, float]:
        total = sum(self.weights.values())
        if total <= 0:
            return dict.fromkeys(self.weights.keys(), 0.0)
        return {k: v / total for k, v in self.weights.items()}


class SimilarityMatcher:
    """Weighted cosine similarity over a fixed feature axis."""

    def __init__(
        self,
        feature_names: list[str],
        *,
        weights: Mapping[str, float] | None = None,
    ) -> None:
        self.feature_names = list(feature_names)
        raw = dict(weights) if weights else {
            n: DEFAULT_REGION_WEIGHTS.get(n, 1.0 / len(self.feature_names))
            for n in self.feature_names
        }
        # Pad for any missing key + auto-normalise to sum-1.
        for n in self.feature_names:
            raw.setdefault(n, 0.0)
        total = sum(raw.values()) or 1.0
        self.weights = {n: float(raw[n]) / total for n in self.feature_names}

    @property
    def weight_vector(self) -> npt.NDArray[np.float64]:
        return np.array(
            [self.weights[n] for n in self.feature_names], dtype=np.float64
        )

    def similarity(
        self,
        a: npt.NDArray[np.float64],
        b: npt.NDArray[np.float64],
    ) -> float:
        """Single pair weighted-cosine. Returns ``0.0`` for null inputs."""
        if a.size == 0 or b.size == 0:
            return 0.0
        w = self.weight_vector
        wa = a * w
        wb = b * w
        denom = float(np.linalg.norm(wa) * np.linalg.norm(wb))
        if denom < 1e-12:
            return 0.0
        return float(np.dot(wa, wb) / denom)

    def topk(
        self,
        query: npt.NDArray[np.float64],
        candidates: npt.NDArray[np.float64],
        *,
        k: int = 5,
    ) -> list[tuple[int, float]]:
        """Return ``[(row_idx, score)]`` for the top-K candidates."""
        if candidates.size == 0:
            return []
        scores = np.array(
            [self.similarity(query, candidates[i]) for i in range(candidates.shape[0])]
        )
        order = np.argsort(-scores)[:k]
        return [(int(i), float(round(scores[i], 4))) for i in order]


@dataclass(slots=True)
class WeightedSimilarityResult:
    """Convenience container — used by the recommender for transport."""

    rank: int
    score: float
    feature_breakdown: dict[str, float] = field(default_factory=dict)
