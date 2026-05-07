"""Cross-scenario analysis endpoints.

Wires the Scenario A/B/C analyzers behind a Redis cache. Each endpoint
returns the standard envelope ``{ data, meta, error }``.
"""

from __future__ import annotations

import time
from dataclasses import asdict, is_dataclass
from datetime import date
from typing import Any

from fastapi import APIRouter, status

from src.analysis.scenario_a import (
    CompensationImpactModel,
    ImpactZoneExtractor,
    RoadImpactAnalyzer,
)
from src.analysis.scenario_b import ThreeVariableAnalyzer
from src.analysis.scenario_c import (
    FeatureExtractor,
    LandValuePredictor,
    RationaleGenerator,
    StoreImpactAnalyzer,
    SuitabilityModel,
)
from src.api.cache import cached_compute
from src.api.deps import DbSession
from src.core.exceptions import NotFoundError
from src.schemas.analysis import (
    LandSuitabilityRequest,
    ScenarioARequest,
    ScenarioBRequest,
    StoreImpactRequest,
)

router = APIRouter()


def _envelope(data: Any, meta: dict[str, Any]) -> dict[str, Any]:
    return {"data": _serialize(data), "meta": meta, "error": None}


def _serialize(value: Any) -> Any:
    """Recursively turn dataclasses / enums into JSON-friendly values."""
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


# ─── Helpers ────────────────────────────────────────────────────────────────


async def _scenario_a_run(
    *,
    db: DbSession,
    body: ScenarioARequest,
) -> dict[str, Any]:
    """Stitch together the Scenario A pipeline for caching."""
    project_row = await _fetch_project(db, body.project_id)
    if project_row is None:
        raise NotFoundError(f"Project not found: id={body.project_id}")

    anchor_date = project_row["anchor_date"] or project_row["planned_announcement_date"]
    if anchor_date is None:
        raise NotFoundError(
            f"Project {body.project_id} has no compensation/announcement anchor date."
        )

    # Fit on whatever historical projects share the same type.
    # Phase 2: load reference samples from the impact view.
    from src.analysis.scenario_a.compensation_model import (  # noqa: PLC0415
        ReferenceProject,
    )

    references: list[ReferenceProject] = []
    model = CompensationImpactModel()
    if references:
        model.fit(references)
    prediction = model.predict(
        anchor_date,
        distances_m=body.distances_m,
        horizons_months=body.horizons_months,
    )

    zone = await ImpactZoneExtractor(db).extract(
        project_id=body.project_id, radius_m=body.radius_m
    )
    roads = await RoadImpactAnalyzer(db).analyze(
        project_id=body.project_id, radius_m=min(body.radius_m, 5_000.0)
    )

    return {
        "project_id": body.project_id,
        "anchor_date": anchor_date.isoformat(),
        "impact_series": _serialize(list(prediction.series)),
        "zones": _serialize(list(zone.rows)),
        "roads": _serialize(list(roads)),
        "model_meta": {
            "model_version": prediction.model_version,
            "confidence_score": prediction.confidence_score,
            "top_factors": prediction.top_factors,
            "notes": prediction.notes,
        },
    }


async def _fetch_project(db: DbSession, project_id: int) -> dict[str, Any] | None:
    from sqlalchemy import bindparam, text  # noqa: PLC0415

    sql = text(
        """
        SELECT
            p.id, p.name, p.planned_announcement_date,
            (
                SELECT MIN(occurred_at) FROM project_stages
                WHERE project_id = p.id AND stage = 'compensation_started'
            ) AS anchor_date
        FROM projects p
        WHERE p.id = :id
        """
    ).bindparams(bindparam("id", value=project_id))
    row = (await db.execute(sql)).mappings().first()
    return dict(row) if row else None


# ─── Routes ─────────────────────────────────────────────────────────────────


@router.post(
    "/scenario-a",
    status_code=status.HTTP_200_OK,
    summary="Scenario A — compensation impact regression",
)
async def run_scenario_a(body: ScenarioARequest, db: DbSession) -> dict[str, Any]:
    started = time.perf_counter()
    payload = body.model_dump(mode="json")

    async def compute() -> dict[str, Any]:
        return await _scenario_a_run(db=db, body=body)

    result, info = await cached_compute(
        session=db,
        scenario="a",
        entity_type="project",
        entity_id=str(body.project_id),
        payload=payload,
        compute=compute,
    )
    elapsed = (time.perf_counter() - started) * 1_000
    meta = {
        **result.get("model_meta", {}),
        "cache_hit": info["cache_hit"],
        "computation_time_ms": round(elapsed, 2),
    }
    return _envelope(
        {
            "project_id": result["project_id"],
            "anchor_date": result["anchor_date"],
            "impact_series": result["impact_series"],
            "zones": result["zones"],
            "roads": result["roads"],
        },
        meta,
    )


@router.post(
    "/scenario-b",
    status_code=status.HTTP_200_OK,
    summary="Scenario B — road × population × traffic",
)
async def run_scenario_b(body: ScenarioBRequest, db: DbSession) -> dict[str, Any]:
    started = time.perf_counter()
    payload = body.model_dump(mode="json")

    async def compute() -> dict[str, Any]:
        result = await ThreeVariableAnalyzer(db).analyze(
            road_id=body.road_id, start=body.start, end=body.end
        )
        return {
            "road_id": result.road_id,
            "time_points": _serialize(result.time_points),
            "correlation_variables": result.correlations.variables,
            "correlation_matrix": result.correlations.matrix,
            "lead_lag": (
                _serialize(result.lead_lag) if result.lead_lag is not None else None
            ),
            "insights": _serialize(result.insights),
            "model_meta": {
                "model_version": result.model_version,
                "confidence_score": result.confidence_score,
                "top_factors": result.top_factors,
            },
        }

    result, info = await cached_compute(
        session=db,
        scenario="b",
        entity_type="road",
        entity_id=str(body.road_id),
        payload=payload,
        compute=compute,
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


@router.post(
    "/scenario-c/store-impact",
    status_code=status.HTTP_200_OK,
    summary="Scenario C — store halo effect",
)
async def run_store_impact(
    body: StoreImpactRequest, db: DbSession
) -> dict[str, Any]:
    started = time.perf_counter()
    payload = body.model_dump(mode="json")

    async def compute() -> dict[str, Any]:
        analyzer = StoreImpactAnalyzer(db)
        bands = tuple(body.bands_m) if body.bands_m else (500, 1_000, 2_000, 3_000)
        result = await analyzer.analyze(body.store_id, bands_m=bands)
        if result is None:
            raise NotFoundError(f"Store not found or has no opened_at: id={body.store_id}")
        return {
            "store_id": result.store_id,
            "open_date": result.open_date.isoformat(),
            "bands": _serialize(result.bands),
            "model_meta": {
                "model_version": result.model_version,
                "confidence_score": result.confidence_score,
                "notes": result.notes,
            },
        }

    result, info = await cached_compute(
        session=db,
        scenario="c",
        entity_type="store_impact",
        entity_id=str(body.store_id),
        payload=payload,
        compute=compute,
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


@router.post(
    "/scenario-c/land-suitability",
    status_code=status.HTTP_200_OK,
    summary="Scenario C — DT/DI suitability score",
)
async def run_land_suitability(
    body: LandSuitabilityRequest, db: DbSession
) -> dict[str, Any]:
    started = time.perf_counter()
    payload = body.model_dump(mode="json")

    if not body.pnu and (body.lat is None or body.lng is None):
        raise NotFoundError("Provide either `pnu` or both `lat` and `lng`.")

    async def compute() -> dict[str, Any]:
        extractor = FeatureExtractor(db)
        if body.pnu:
            vec = await extractor.extract_for_pnu(body.pnu, snapshot_date=body.snapshot_date)
            if vec is None:
                raise NotFoundError(f"No building row for PNU={body.pnu!r}")
        else:
            vec = await extractor.extract_for_location(
                lat=body.lat,  # type: ignore[arg-type]
                lng=body.lng,  # type: ignore[arg-type]
                snapshot_date=body.snapshot_date,
            )

        # Lazy-load model from app.state.model_registry; if missing, return
        # neutral score so the API is still useful pre-training.
        from src.core.config import get_settings  # noqa: PLC0415
        from src.ml.registry import build_registry  # noqa: PLC0415

        settings = get_settings()
        registry = build_registry()
        cached = registry.get(f"suitability_{body.target.lower()}", "v1")
        if cached is None:
            try:
                cached = SuitabilityModel.load(
                    settings.models_dir / f"suitability_{body.target.lower()}_v1.pkl"
                )
            except FileNotFoundError:
                cached = None

        rationales: list[dict[str, Any]] = []
        if cached is None:
            score_raw = 0.5
            score_100 = 50
            label = "medium"
            top_factors: list[dict[str, Any]] = []
            confidence = 0.20
            notes = ["Suitability model not trained yet — neutral score returned."]
        else:
            prediction = cached.predict(vec)
            explanation = cached.explain(vec, top_n=3)
            score_raw = prediction.score_raw
            score_100 = prediction.score_100
            label = prediction.label
            top_factors = explanation.top_factors
            confidence = explanation.confidence_score
            notes = []
            shap_for_rules = top_factors if top_factors and "shap" in top_factors[0] else None
            rationales = [
                {
                    "category": r.category.value,
                    "impact": r.impact.value,
                    "feature": r.feature,
                    "value": r.value,
                    "detail": r.detail,
                }
                for r in RationaleGenerator().generate(
                    vec, shap_contributions=shap_for_rules
                )
            ]

        forecast_payload: dict[str, Any] | None = None
        if vec.pnu:
            try:
                forecast = await LandValuePredictor(db).forecast(vec.pnu)
                forecast_payload = forecast.forecast
            except Exception:  # noqa: BLE001
                forecast_payload = None

        return {
            "pnu": vec.pnu,
            "target": body.target,
            "score_raw": score_raw,
            "score_100": score_100,
            "label": label,
            "rationales": rationales,
            "value_forecast": forecast_payload,
            "model_meta": {
                "model_version": (cached.model_version if cached else "untrained"),
                "confidence_score": confidence,
                "top_factors": top_factors,
                "notes": notes,
            },
        }

    entity_id = body.pnu or f"{body.lat:.5f}_{body.lng:.5f}"
    result, info = await cached_compute(
        session=db,
        scenario="c",
        entity_type=f"suitability_{body.target.lower()}",
        entity_id=entity_id,
        payload=payload,
        compute=compute,
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


# ─── Existing read-only routes (kept from Stage 1) ─────────────────────────


@router.get("/runs", summary="List analysis runs")
async def list_runs() -> dict[str, Any]:
    """List recent analysis runs across all scenarios.

    TODO: Stage 4에서 페이지네이션 + scenario / status 필터 추가.
    """
    return {"data": None, "meta": {"status": "not_implemented"}, "error": None}


@router.get("/runs/{run_id}", summary="Get one run")
async def get_run(run_id: str) -> dict[str, Any]:
    return {
        "data": None,
        "meta": {"status": "not_implemented", "run_id": run_id},
        "error": None,
    }


@router.get("/runs/{run_id}/results", summary="Get run results")
async def get_run_results(run_id: str) -> dict[str, Any]:
    return {
        "data": None,
        "meta": {"status": "not_implemented", "run_id": run_id},
        "error": None,
    }
