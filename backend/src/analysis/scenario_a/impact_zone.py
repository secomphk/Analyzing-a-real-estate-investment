"""Extract the spatial zone affected by a project + its admin-area overlap.

Uses PostGIS ``ST_Buffer`` + ``ST_Intersects`` so we don't have to load
geometries into Python. The result is a list of ``ImpactZoneRow`` rows
keyed by admin code, ordered by distance to the project boundary.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(slots=True, frozen=True)
class ImpactZoneRow:
    """One admin area inside the impact zone."""

    admin_code: str
    admin_name: str
    distance_m: float
    expected_uplift_pct: float | None = None


@dataclass(slots=True)
class ImpactZone:
    """Buffered impact zone description for the API response."""

    project_id: int
    radius_m: float
    rows: list[ImpactZoneRow]


class ImpactZoneExtractor:
    """PostGIS-backed impact-zone resolver."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def extract(
        self,
        *,
        project_id: int,
        radius_m: float = 5_000.0,
    ) -> ImpactZone:
        """Return admin areas overlapping a buffer around the project.

        The query reads project geometry from ``projects`` and computes
        each admin area's centroid distance to the project boundary using
        ``geography`` casts so distances are in meters.
        """
        sql = text(
            """
            WITH p AS (
                SELECT id, name, geometry, centroid
                FROM projects
                WHERE id = :project_id
            )
            SELECT
                a.code             AS admin_code,
                a.name             AS admin_name,
                ST_Distance(
                    p.geometry::geography,
                    a.centroid::geography
                ) AS distance_m
            FROM admin_areas a, p
            WHERE p.geometry IS NOT NULL
              AND a.centroid  IS NOT NULL
              AND ST_DWithin(
                  p.geometry::geography,
                  a.centroid::geography,
                  :radius_m
              )
            ORDER BY distance_m ASC
            """
        ).bindparams(
            bindparam("project_id", value=project_id),
            bindparam("radius_m", value=radius_m),
        )
        result = await self._session.execute(sql)
        rows = [
            ImpactZoneRow(
                admin_code=str(r.admin_code),
                admin_name=str(r.admin_name),
                distance_m=float(r.distance_m),
            )
            for r in result
        ]
        return ImpactZone(project_id=project_id, radius_m=radius_m, rows=rows)
