"""Scenario C inference endpoints.

The DT-candidates endpoint is the heavyweight Scenario C entry point: it
scans every commercial parcel in a 시군구, scores them with the suitability
model, and returns the top-N enriched with rationales + forecasts.
"""

from __future__ import annotations

import time
from dataclasses import asdict, is_dataclass
from datetime import date
from typing import Any

from fastapi import APIRouter, status

from src.analysis.scenario_c import (
    CandidateFinder,
    FeatureExtractor,
    LandValuePredictor,
    RationaleGenerator,
    SuitabilityModel,
)
from src.api.cache import cached_compute
from src.api.deps import DbSession
from src.core.config import get_settings
from src.core.exceptions import ModelNotLoadedError
from src.ml.registry import build_registry
from src.schemas.analysis import DTCandidatesRequest

router = APIRouter()


def _envelope(data: Any, meta: dict[str, Any]) -> dict[str, Any]:
    return {"data": _serialize(data), "meta": meta, "error": None}


def _serialize(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _serialize(asdict(value))
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_serialize(v) for v in value]
    if hasattr(value, "value") and hasattr(type(value), "_member_map_"):
        return value.value
    if isinstance(value, date):
        return value.isoformat()
    return value


def _load_suitability(target: str) -> SuitabilityModel:
    """Load (or raise) the suitability model for ``target``."""
    settings = get_settings()
    registry = build_registry()
    name = f"suitability_{target.lower()}"
    if (model := registry.get(name, "v1")) is not None:
        return model  # type: ignore[no-any-return]
    try:
        return SuitabilityModel.load(settings.models_dir / f"{name}_v1.pkl")
    except FileNotFoundError as exc:
        raise ModelNotLoadedError(
            f"Suitability model for {target} not trained yet. "
            "Run `python -m src.analysis.training.train_suitability --target "
            f"{target}` first.",
        ) from exc


@router.post(
    "/dt-candidates",
    status_code=status.HTTP_200_OK,
    summary="Top-N DT/DI candidate parcels for a 시군구",
)
async def dt_candidates(body: DTCandidatesRequest, db: DbSession) -> dict[str, Any]:
    """Scan candidate parcels in ``region_code`` and return the top scorers."""
    started = time.perf_counter()
    payload = body.model_dump(mode="json")

    async def compute() -> dict[str, Any]:
        suitability = _load_suitability(body.target)
        finder = CandidateFinder(
            session=db,
            suitability=suitability,
            feature_extractor=FeatureExtractor(db),
            value_predictor=LandValuePredictor(db),
            rationale_generator=RationaleGenerator(),
        )
        ranking = await finder.find(region_code=body.region_code, top_n=body.top_n)
        return {
            "region_code": ranking.region_code,
            "target": ranking.target,
            "candidates": _serialize(ranking.candidates),
            "model_meta": {
                "model_version": ranking.model_version,
                "confidence_score": ranking.confidence_score,
                "notes": ranking.notes,
            },
        }

    result, info = await cached_compute(
        session=db,
        scenario="c",
        entity_type=f"candidates_{body.target.lower()}",
        entity_id=body.region_code,
        payload=payload,
        compute=compute,
        ttl_seconds=15 * 60,
    )
    elapsed = (time.perf_counter() - started) * 1_000
    meta = {
        **result.get("model_meta", {}),
        "cache_hit": info["cache_hit"],
        "computation_time_ms": round(elapsed, 2),
    }
    return _envelope(
        {k: v for k, v in result.items() if k != "model_meta"}, meta
    )


# ─── Stage 1 stubs (kept) ──────────────────────────────────────────────────


@router.post("/suitability/dt", summary="DT store suitability score (legacy)")
async def predict_dt_suitability() -> dict[str, Any]:
    return {
        "data": None,
        "meta": {"status": "deprecated",
                 "use": "/api/v1/analysis/scenario-c/land-suitability"},
        "error": None,
    }


@router.post("/suitability/di", summary="DI store suitability score (legacy)")
async def predict_di_suitability() -> dict[str, Any]:
    return {
        "data": None,
        "meta": {"status": "deprecated",
                 "use": "/api/v1/analysis/scenario-c/land-suitability"},
        "error": None,
    }


@router.post("/revenue/forecast", summary="Revenue forecast (Phase 2)")
async def forecast_revenue() -> dict[str, Any]:
    return {
        "data": None,
        "meta": {"status": "not_implemented",
                 "phase": "Phase 2: Prophet + XGBoost residual model"},
        "error": None,
    }
