"""Scenario B — road segment endpoints.

The analysis trigger lives at ``POST /api/v1/analysis/scenario-b``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, status
from sqlalchemy import bindparam, text

from src.api.deps import DbSession
from src.core.exceptions import NotFoundError

router = APIRouter()


def _envelope(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"data": data, "meta": meta or {}, "error": None}


@router.get("", status_code=status.HTTP_200_OK, summary="List road segments")
async def list_roads(
    db: DbSession,
    region_code: str | None = Query(default=None, min_length=2, max_length=10),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    sql = text(
        """
        SELECT
            rs.id, rs.name, rs.route_no, rs.region_code, rs.length_m,
            (
                SELECT COUNT(*) FROM road_expansion_stages WHERE road_id = rs.id
            ) AS stage_count
        FROM road_segments rs
        WHERE (CAST(:region_code AS text) IS NULL OR rs.region_code = :region_code)
        ORDER BY rs.id
        LIMIT :limit OFFSET :offset
        """
    ).bindparams(
        bindparam("region_code", value=region_code),
        bindparam("limit", value=limit),
        bindparam("offset", value=offset),
    )
    rows = (await db.execute(sql)).mappings().all()
    return _envelope(
        [dict(r) for r in rows],
        {"limit": limit, "offset": offset, "count": len(rows)},
    )


@router.get("/{road_id}", summary="Get one road + stages")
async def get_road(road_id: int, db: DbSession) -> dict[str, Any]:
    sql_road = text(
        """
        SELECT id, name, route_no, region_code, length_m, description, source
        FROM road_segments
        WHERE id = :id
        """
    ).bindparams(bindparam("id", value=road_id))
    row = (await db.execute(sql_road)).mappings().first()
    if row is None:
        raise NotFoundError(f"Road segment not found: id={road_id}")

    sql_stages = text(
        """
        SELECT id, stage, occurred_at, lanes_before, lanes_after,
               width_before_m, width_after_m, note, source
        FROM road_expansion_stages
        WHERE road_id = :id
        ORDER BY occurred_at
        """
    ).bindparams(bindparam("id", value=road_id))
    stages = [dict(r) for r in (await db.execute(sql_stages)).mappings().all()]
    return _envelope({**dict(row), "stages": stages})


@router.post(
    "/{road_id}/analyze",
    status_code=status.HTTP_303_SEE_OTHER,
    summary="(deprecated) — use POST /api/v1/analysis/scenario-b instead",
)
async def analyze_road(road_id: int) -> dict[str, Any]:
    return {
        "data": None,
        "meta": {
            "status": "deprecated",
            "use": "/api/v1/analysis/scenario-b",
            "road_id": road_id,
        },
        "error": None,
    }
