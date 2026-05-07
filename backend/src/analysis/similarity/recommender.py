"""High-level recommender that wires the matcher to the persistence layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.analysis.similarity.feature_extractor import (
    REGION_FEATURE_NAMES,
    RegionFeatureExtractor,
)
from src.analysis.similarity.matcher import SimilarityMatcher


@dataclass(slots=True, frozen=True)
class RecommendationItem:
    """One ranked recommendation."""

    target_entity_type: str
    target_entity_id: str
    target_label: str | None
    score: float
    rank: int
    breakdown: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RecommenderResult:
    """Full recommender response."""

    source_entity_type: str
    source_entity_id: str
    items: list[RecommendationItem]
    model_version: str = "similarity_v1.0.0"
    confidence_score: float = 0.5


class Recommender:
    """Recommend similar regions for a given source admin area.

    Currently focused on Scenario B (region similarity). Scenario C uses
    the FAISS index directly via :class:`StoreSimilarityIndex`.
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        matcher: SimilarityMatcher | None = None,
    ) -> None:
        self._session = session
        self._features = RegionFeatureExtractor(session)
        self._matcher = matcher or SimilarityMatcher(REGION_FEATURE_NAMES)

    async def similar_regions(
        self,
        *,
        source_admin_code: str,
        candidate_admin_codes: list[str] | None = None,
        top_n: int = 10,
    ) -> RecommenderResult:
        # Default the candidate list to every admin area in the same level.
        candidates = candidate_admin_codes or await self._fetch_peer_admin_codes(
            source_admin_code
        )
        codes = list({source_admin_code, *candidates})
        vectors = await self._features.extract(codes)
        by_code = {v.admin_code: v for v in vectors}
        if source_admin_code not in by_code:
            return RecommenderResult(
                source_entity_type="region",
                source_entity_id=source_admin_code,
                items=[],
                confidence_score=0.0,
            )

        source_vec = by_code[source_admin_code].to_array()
        cand_codes = [c for c in candidates if c != source_admin_code and c in by_code]
        if not cand_codes:
            return RecommenderResult(
                source_entity_type="region",
                source_entity_id=source_admin_code,
                items=[],
                confidence_score=0.0,
            )
        cand_matrix = np.vstack([by_code[c].to_array() for c in cand_codes])
        ranked = self._matcher.topk(source_vec, cand_matrix, k=top_n)

        items = [
            RecommendationItem(
                target_entity_type="region",
                target_entity_id=cand_codes[idx],
                target_label=by_code[cand_codes[idx]].name,
                score=score,
                rank=rank + 1,
                breakdown={
                    name: float(by_code[cand_codes[idx]].values.get(name, 0.0))
                    for name in self._matcher.feature_names
                },
            )
            for rank, (idx, score) in enumerate(ranked)
        ]
        confidence = round(min(0.40 + 0.05 * len(items), 0.85), 3)

        return RecommenderResult(
            source_entity_type="region",
            source_entity_id=source_admin_code,
            items=items,
            confidence_score=confidence,
        )

    async def _fetch_peer_admin_codes(self, code: str) -> list[str]:
        """Pick siblings at the same admin level (e.g. all 시·군·구)."""
        sql = text(
            """
            WITH src AS (SELECT level FROM admin_areas WHERE code = :code)
            SELECT code FROM admin_areas, src
            WHERE admin_areas.level = src.level
              AND admin_areas.code <> :code
            ORDER BY admin_areas.code
            LIMIT 100
            """
        ).bindparams(bindparam("code", value=code))
        return [r.code for r in (await self._session.execute(sql)).all()]
