"""Recommendation endpoints — region similarity (Scenario B) + store similarity (C)."""

from __future__ import annotations

import time
from dataclasses import asdict, is_dataclass
from datetime import date
from typing import Any

from fastapi import APIRouter, status
from sqlalchemy import bindparam, text

from src.analysis.scenario_c.feature_engineering import FeatureExtractor
from src.analysis.scenario_c.similarity_search import StoreSimilarityIndex
from src.analysis.similarity import Recommender
from src.api.cache import cached_compute
from src.api.deps import DbSession
from src.core.config import get_settings
from src.core.exceptions import NotFoundError
from src.schemas.analysis import RecommendationsRequest

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


@router.post(
    "",
    status_code=status.HTTP_200_OK,
    summary="Region or store similarity recommendations",
)
async def recommend(body: RecommendationsRequest, db: DbSession) -> dict[str, Any]:
    started = time.perf_counter()
    payload = body.model_dump(mode="json")

    async def compute() -> dict[str, Any]:
        if body.source_entity_type == "region":
            result = await Recommender(db).similar_regions(
                source_admin_code=body.source_entity_id, top_n=body.top_n,
            )
            return {
                "source_entity_type": result.source_entity_type,
                "source_entity_id": result.source_entity_id,
                "items": _serialize(result.items),
                "model_meta": {
                    "model_version": result.model_version,
                    "confidence_score": result.confidence_score,
                },
            }

        # ─── Scenario C: store similarity via FAISS ───────────────────
        store_id = int(body.source_entity_id)
        meta_row = await _fetch_store_meta(db, store_id)
        if meta_row is None:
            raise NotFoundError(f"Store not found: id={store_id}")

        try:
            index = StoreSimilarityIndex.load(get_settings().models_dir, version="v1")
        except FileNotFoundError as exc:
            raise NotFoundError(
                "Store similarity index not built yet. "
                "Run `python -m src.analysis.training.build_faiss_index` first."
            ) from exc

        vec = await FeatureExtractor(db).extract_for_store(store_id)
        if vec is None:
            raise NotFoundError(f"Could not extract features for store {store_id}.")

        results = index.search(
            vec.to_array().astype("float32"),
            top_n=body.top_n,
            exclude_store_id=store_id,
        )
        labels = await _fetch_store_labels(db, [r.store_id for r in results])
        items = [
            {
                "target_entity_type": "store",
                "target_entity_id": str(r.store_id),
                "target_label": labels.get(r.store_id),
                "score": r.score,
                "rank": r.rank,
            }
            for r in results
        ]
        return {
            "source_entity_type": "store",
            "source_entity_id": str(store_id),
            "items": items,
            "model_meta": {
                "model_version": "faiss_store_v1",
                "confidence_score": 0.75 if items else 0.0,
            },
        }

    result, info = await cached_compute(
        session=db,
        scenario="similarity",
        entity_type=body.source_entity_type,
        entity_id=str(body.source_entity_id),
        payload=payload,
        compute=compute,
        ttl_seconds=10 * 60,
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


# ─── Legacy GET routes (kept for backward compatibility) ───────────────────


@router.get("/regions/{region_code}", summary="Similar regions (legacy GET)")
async def similar_regions(
    region_code: str, db: DbSession, k: int = 10
) -> dict[str, Any]:
    body = RecommendationsRequest(
        source_entity_type="region",
        source_entity_id=region_code,
        top_n=k,
    )
    return await recommend(body, db)


@router.get("/stores/{store_id}", summary="Similar stores (legacy GET)")
async def similar_stores(
    store_id: int, db: DbSession, k: int = 10
) -> dict[str, Any]:
    body = RecommendationsRequest(
        source_entity_type="store",
        source_entity_id=str(store_id),
        top_n=k,
    )
    return await recommend(body, db)


# ─── Helpers ────────────────────────────────────────────────────────────────


async def _fetch_store_meta(db: DbSession, store_id: int) -> dict[str, Any] | None:
    sql = text("SELECT id, name FROM stores WHERE id = :id").bindparams(
        bindparam("id", value=store_id)
    )
    row = (await db.execute(sql)).mappings().first()
    return dict(row) if row else None


async def _fetch_store_labels(
    db: DbSession, store_ids: list[int]
) -> dict[int, str]:
    if not store_ids:
        return {}
    sql = text(
        "SELECT id, name FROM stores WHERE id = ANY(:ids)"
    ).bindparams(bindparam("ids", value=store_ids))
    return {int(r.id): str(r.name) for r in (await db.execute(sql)).all()}
