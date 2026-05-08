"""Scenario A — public-housing district compensation project endpoints.

Read endpoints (list/get) hit the DB directly; the analysis trigger now
lives at ``POST /api/v1/analysis/scenario-a`` (see ``analysis.py``).
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


@router.get("", status_code=status.HTTP_200_OK, summary="List compensation projects")
async def list_projects(
    db: DbSession,
    region_code: str | None = Query(default=None, min_length=2, max_length=10),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    sql = text(
        """
        SELECT
            p.id, p.name, p.project_type, p.region_code,
            -- Cast NUMERIC → DOUBLE PRECISION so the JSON encoder emits
            -- a number instead of a string ("7600.00"). The frontend
            -- Zod schemas declare these as ``z.number()`` and reject
            -- string-shaped numbers.
            p.area_ha::double precision AS area_ha,
            p.expected_compensation_billion_krw::double precision
                AS expected_compensation_billion_krw,
            p.planned_announcement_date, p.planned_completion_date,
            (SELECT COUNT(*) FROM project_stages WHERE project_id = p.id) AS stage_count
        FROM projects p
        WHERE (CAST(:region_code AS text) IS NULL OR p.region_code = :region_code)
        ORDER BY p.id
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


@router.post("", status_code=status.HTTP_202_ACCEPTED, summary="Register a new project")
async def create_project() -> dict[str, Any]:
    """Stage 4 will accept full project payloads + boundary GeoJSON."""
    return {
        "data": None,
        "meta": {"status": "not_implemented"},
        "error": None,
    }


@router.get("/{project_id}", summary="Get one project + stages")
async def get_project(project_id: int, db: DbSession) -> dict[str, Any]:
    sql_project = text(
        """
        SELECT p.id, p.name, p.project_type, p.region_code,
               p.area_ha::double precision AS area_ha,
               p.expected_compensation_billion_krw::double precision
                   AS expected_compensation_billion_krw,
               p.planned_announcement_date, p.planned_completion_date,
               p.description, p.source
        FROM projects p
        WHERE p.id = :id
        """
    ).bindparams(bindparam("id", value=project_id))
    project_row = (await db.execute(sql_project)).mappings().first()
    if project_row is None:
        raise NotFoundError(f"Project not found: id={project_id}")

    sql_stages = text(
        """
        SELECT id, stage, occurred_at, sequence_no, note, source
        FROM project_stages
        WHERE project_id = :id
        ORDER BY occurred_at
        """
    ).bindparams(bindparam("id", value=project_id))
    stages = [
        dict(r) for r in (await db.execute(sql_stages)).mappings().all()
    ]
    return _envelope({**dict(project_row), "stages": stages})


@router.post(
    "/{project_id}/analyze",
    status_code=status.HTTP_303_SEE_OTHER,
    summary="(deprecated) — use POST /api/v1/analysis/scenario-a instead",
)
async def analyze_project(project_id: int) -> dict[str, Any]:
    return {
        "data": None,
        "meta": {
            "status": "deprecated",
            "use": "/api/v1/analysis/scenario-a",
            "project_id": project_id,
        },
        "error": None,
    }
