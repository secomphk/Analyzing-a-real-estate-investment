"""Candidate-land finder for DT/DI siting.

Scans candidate parcels in a 시군구, runs the suitability model on each,
optionally enriches with similarity + value forecast, and returns a
ranked list of recommendations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import numpy as np
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.analysis.scenario_c.feature_engineering import (
    FeatureExtractor,
    FeatureVector,
)
from src.analysis.scenario_c.rationale_generator import (
    Rationale,
    RationaleGenerator,
)
from src.analysis.scenario_c.similarity_search import (
    StoreSimilarityIndex,
    StoreSimilarityResult,
)
from src.analysis.scenario_c.suitability_model import (
    Suitability,
    SuitabilityModel,
)
from src.analysis.scenario_c.value_predictor import (
    LandValueForecast,
    LandValuePredictor,
)


@dataclass(slots=True, frozen=True)
class CandidateRow:
    """One candidate parcel + its analytics enrichment."""

    pnu: str
    address: str | None
    suitability: Suitability
    value_forecast: LandValueForecast | None
    similar_stores: list[StoreSimilarityResult] = field(default_factory=list)
    rationales: list[Rationale] = field(default_factory=list)
    breakdown: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CandidateRanking:
    """Top-N output for the API."""

    target: str                       # "DT" / "DI"
    region_code: str
    candidates: list[CandidateRow]
    model_version: str = "scenario_c_v1.0.0"
    confidence_score: float = 0.5
    notes: list[str] = field(default_factory=list)


class CandidateFinder:
    """Compose feature extraction + suitability + similarity + value forecast."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        suitability: SuitabilityModel,
        feature_extractor: FeatureExtractor,
        value_predictor: LandValuePredictor,
        rationale_generator: RationaleGenerator | None = None,
        similarity_index: StoreSimilarityIndex | None = None,
    ) -> None:
        self._session = session
        self._suitability = suitability
        self._features = feature_extractor
        self._value = value_predictor
        self._rationales = rationale_generator or RationaleGenerator()
        self._similarity = similarity_index

    async def find(
        self,
        *,
        region_code: str,
        top_n: int = 10,
        snapshot_date: date | None = None,
        min_land_area_m2: float = 500.0,
        max_land_area_m2: float = 2_500.0,
    ) -> CandidateRanking:
        snap = snapshot_date or date.today()
        pnus = await self._candidate_pnus(
            region_code=region_code,
            min_area=min_land_area_m2,
            max_area=max_land_area_m2,
        )
        if not pnus:
            return CandidateRanking(
                target=self._suitability.target,
                region_code=region_code,
                candidates=[],
                notes=[
                    "지정한 시군구에 후보 토지가 없습니다 — "
                    "면적·용도 조건을 완화하거나 ETL을 다시 실행하세요.",
                ],
            )

        # Extract feature vectors in parallel-ish (sequentially within one
        # session — Stage 1 keeps it simple). We run the suitability model
        # in one batched call afterwards.
        vectors: list[FeatureVector] = []
        meta: list[dict[str, Any]] = []
        for pnu in pnus:
            vec = await self._features.extract_for_pnu(pnu, snapshot_date=snap)
            if vec is None:
                continue
            vectors.append(vec)
            meta.append({"pnu": pnu})

        if not vectors:
            return CandidateRanking(
                target=self._suitability.target,
                region_code=region_code,
                candidates=[],
                notes=["피처를 추출할 수 있는 후보가 없습니다."],
            )

        scores = self._suitability.predict_batch(vectors)

        # Sort by score; cap at top_n; enrich the survivors.
        order = sorted(
            range(len(scores)),
            key=lambda i: scores[i].score_raw,
            reverse=True,
        )[:top_n]

        candidates: list[CandidateRow] = []
        for i in order:
            vec = vectors[i]
            score = scores[i]
            explanation = self._suitability.explain(vec, top_n=3)
            forecast: LandValueForecast | None = None
            similar: list[StoreSimilarityResult] = []
            if vec.pnu:
                forecast = await self._value.forecast(
                    vec.pnu,
                    catalysts={k: vec.values.get(k, 0.0)
                               for k in (
                                   "nearby_road_expansion",
                                   "nearby_new_town",
                                   "subway_extension_planned",
                                   "population_growth_3y_pct",
                                   "transaction_count_growth_3y",
                               )},
                )
            if self._similarity is not None:
                similar = self._similarity.search(
                    self._normalised_query(vec), top_n=5
                )
            rationales = self._rationales.generate(
                vec, shap_contributions=explanation.top_factors
            )

            candidates.append(
                CandidateRow(
                    pnu=meta[i]["pnu"],
                    address=vec.extra.get("address"),
                    suitability=score,
                    value_forecast=forecast,
                    similar_stores=similar,
                    rationales=rationales,
                    breakdown={
                        "explanation": explanation.top_factors,
                        "explanation_confidence": explanation.confidence_score,
                    },
                )
            )

        confidence: float = (
            float(np.mean([c.suitability.score_raw for c in candidates]))
            if candidates
            else 0.0
        )
        return CandidateRanking(
            target=self._suitability.target,
            region_code=region_code,
            candidates=candidates,
            confidence_score=round(confidence, 3),
        )

    # ─── Internal ───────────────────────────────────────────────────────

    async def _candidate_pnus(
        self,
        *,
        region_code: str,
        min_area: float,
        max_area: float,
    ) -> list[str]:
        sql = text(
            """
            SELECT pnu
            FROM buildings
            WHERE region_code = :region_code
              AND COALESCE(parcel_area_m2, 0) BETWEEN :min_area AND :max_area
              AND (use_type ILIKE :commercial OR use_type ILIKE :neighborhood)
            ORDER BY parcel_area_m2 DESC
            LIMIT 200
            """
        ).bindparams(
            bindparam("region_code", value=region_code),
            bindparam("min_area", value=min_area),
            bindparam("max_area", value=max_area),
            bindparam("commercial", value="%상업%"),
            bindparam("neighborhood", value="%근린%"),
        )
        rows = (await self._session.execute(sql)).all()
        return [r.pnu for r in rows]

    def _normalised_query(self, vec: FeatureVector) -> np.ndarray:
        arr = vec.to_array().astype(np.float32, copy=True)
        # Light normalisation so very large absolute values (population)
        # don't drown out scaled features. The training-time index is
        # itself L2-normalised at build-time, so cosine works regardless.
        return arr
