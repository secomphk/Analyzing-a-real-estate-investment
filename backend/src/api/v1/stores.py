"""Scenario C — store catalog GET endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, status
from sqlalchemy import bindparam, text

from src.api.deps import DbSession
from src.core.exceptions import NotFoundError

router = APIRouter()


def _envelope(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"data": data, "meta": meta or {}, "error": None}


@router.get("", status_code=status.HTTP_200_OK, summary="List stores")
async def list_stores(
    db: DbSession,
    brand: str | None = Query(default=None, max_length=100),
    store_type: str | None = Query(default=None, pattern="^(DT|DI|standard|kiosk)$"),
    region_code: str | None = Query(default=None, min_length=2, max_length=10),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    sql = text(
        """
        SELECT
            s.id, s.name, s.address, s.region_code, s.pnu,
            s.store_type, s.opened_at, s.closed_at,
            s.land_area_m2, s.building_area_m2,
            sb.name AS brand_name, sb.category AS brand_category
        FROM stores s
        JOIN store_brands sb ON sb.id = s.brand_id
        WHERE (CAST(:brand AS text) IS NULL OR sb.name = :brand)
          -- ``store_type`` is a Postgres ENUM; comparing against a text
          -- bind without an explicit cast trips ``DatatypeMismatchError``
          -- on asyncpg, so coerce the bind to the enum type.
          AND (CAST(:store_type AS text) IS NULL OR s.store_type = CAST(:store_type AS store_type))
          AND (CAST(:region_code AS text) IS NULL OR s.region_code = :region_code)
        ORDER BY s.id
        LIMIT :limit OFFSET :offset
        """
    ).bindparams(
        bindparam("brand", value=brand),
        bindparam("store_type", value=store_type),
        bindparam("region_code", value=region_code),
        bindparam("limit", value=limit),
        bindparam("offset", value=offset),
    )
    rows = (await db.execute(sql)).mappings().all()
    return _envelope(
        [dict(r) for r in rows],
        {"limit": limit, "offset": offset, "count": len(rows)},
    )


@router.get("/{store_id}", summary="Get one store")
async def get_store(store_id: int, db: DbSession) -> dict[str, Any]:
    sql = text(
        """
        SELECT
            s.id, s.name, s.address, s.region_code, s.pnu,
            s.store_type, s.opened_at, s.closed_at,
            s.land_area_m2, s.building_area_m2,
            sb.name AS brand_name, sb.category AS brand_category,
            ST_X(s.location) AS lng, ST_Y(s.location) AS lat
        FROM stores s
        JOIN store_brands sb ON sb.id = s.brand_id
        WHERE s.id = :id
        """
    ).bindparams(bindparam("id", value=store_id))
    row = (await db.execute(sql)).mappings().first()
    if row is None:
        raise NotFoundError(f"Store not found: id={store_id}")
    return _envelope(dict(row))


@router.get("/{store_id}/similar", summary="Find similar stores (FAISS)")
async def find_similar_stores(store_id: int, k: int = 10) -> dict[str, Any]:
    """Legacy GET — prefer ``POST /api/v1/recommendations``."""
    return {
        "data": None,
        "meta": {
            "status": "deprecated",
            "use": "/api/v1/recommendations",
            "store_id": store_id,
            "k": k,
        },
        "error": None,
    }
