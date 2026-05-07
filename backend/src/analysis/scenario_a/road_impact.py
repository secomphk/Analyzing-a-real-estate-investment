"""Score nearby roads for a project's impact zone.

Higher scores are given to longer, larger-class roads near the project's
centroid — used as a multiplier on the price-uplift surface.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(slots=True, frozen=True)
class RoadImpactRow:
    """One road and its accessibility contribution."""

    road_id: int
    name: str
    route_no: str | None
    length_m: float | None
    distance_m: float
    weight: float


# Heuristic weights by route prefix. Higher class ⇒ bigger access boost.
_ROUTE_PREFIX_WEIGHT = {
    "고속": 1.0,
    "국도": 0.8,
    "지방도": 0.6,
    "시도": 0.4,
}


def _route_class_weight(route_no: str | None) -> float:
    if not route_no:
        return 0.5
    for prefix, weight in _ROUTE_PREFIX_WEIGHT.items():
        if prefix in route_no:
            return weight
    return 0.5


def _distance_weight(distance_m: float) -> float:
    """Linearly decay 1.0 → 0.0 over a 3 km radius."""
    if distance_m <= 0:
        return 1.0
    return max(0.0, 1.0 - distance_m / 3_000.0)


class RoadImpactAnalyzer:
    """Pull roads inside a project's buffer and score their impact."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def analyze(
        self,
        *,
        project_id: int,
        radius_m: float = 3_000.0,
    ) -> list[RoadImpactRow]:
        sql = text(
            """
            WITH p AS (
                SELECT id, geometry FROM projects WHERE id = :project_id
            )
            SELECT
                rs.id        AS road_id,
                rs.name      AS name,
                rs.route_no  AS route_no,
                rs.length_m  AS length_m,
                ST_Distance(p.geometry::geography, rs.geometry::geography) AS distance_m
            FROM road_segments rs, p
            WHERE p.geometry IS NOT NULL
              AND rs.geometry IS NOT NULL
              AND ST_DWithin(p.geometry::geography, rs.geometry::geography, :radius_m)
            ORDER BY distance_m ASC
            """
        ).bindparams(
            bindparam("project_id", value=project_id),
            bindparam("radius_m", value=radius_m),
        )
        result = await self._session.execute(sql)
        out: list[RoadImpactRow] = []
        for r in result:
            class_w = _route_class_weight(r.route_no)
            dist_w = _distance_weight(float(r.distance_m))
            length_w = min((r.length_m or 0) / 5_000.0, 1.0)
            weight = round(class_w * (0.5 * dist_w + 0.5 * length_w), 3)
            out.append(
                RoadImpactRow(
                    road_id=int(r.road_id),
                    name=str(r.name),
                    route_no=str(r.route_no) if r.route_no else None,
                    length_m=float(r.length_m) if r.length_m else None,
                    distance_m=float(r.distance_m),
                    weight=float(weight),
                )
            )
        return out
