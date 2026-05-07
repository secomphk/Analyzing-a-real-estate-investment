"""Region-level feature extractor for the (Scenario B) recommender.

Each admin area gets a small fixed-length feature vector summarising the
3 Scenario B variables — used by :class:`SimilarityMatcher`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import numpy.typing as npt
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

REGION_FEATURE_NAMES: list[str] = [
    "road_progress",
    "population_avg",
    "population_growth_3y",
    "aadt_avg",
    "aadt_growth_3y",
]


@dataclass(slots=True)
class RegionFeatureVector:
    """Per-admin-area feature row."""

    admin_code: str
    name: str | None
    values: dict[str, float] = field(default_factory=dict)

    def to_array(self) -> npt.NDArray[np.float64]:
        return np.array(
            [float(self.values.get(n, 0.0)) for n in REGION_FEATURE_NAMES],
            dtype=np.float64,
        )


class RegionFeatureExtractor:
    """Pulls the 3-variable summary per admin area from the DB."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def extract(
        self,
        admin_codes: list[str],
        *,
        snapshot_date: date | None = None,
    ) -> list[RegionFeatureVector]:
        if not admin_codes:
            return []
        snap = snapshot_date or date.today()
        sql = text(
            """
            WITH pop AS (
                SELECT
                    region_code,
                    AVG(total_population)::float            AS pop_avg,
                    (
                      MAX(total_population) FILTER (
                          WHERE observed_at >= (:snap::date - INTERVAL '6 month')
                      )::float
                    - MIN(total_population) FILTER (
                          WHERE observed_at >= (:snap::date - INTERVAL '36 month')
                            AND observed_at <= (:snap::date - INTERVAL '30 month')
                      )::float
                    ) / NULLIF(
                      MIN(total_population) FILTER (
                          WHERE observed_at >= (:snap::date - INTERVAL '36 month')
                            AND observed_at <= (:snap::date - INTERVAL '30 month')
                      )::float, 0
                    ) AS pop_growth_3y
                FROM population_stats
                WHERE region_code = ANY(:codes)
                  AND observed_at <= :snap
                GROUP BY region_code
            ),
            road AS (
                SELECT
                    rs.region_code,
                    AVG(tv.aadt)::float AS aadt_avg,
                    (
                      MAX(tv.aadt) FILTER (
                          WHERE tv.observed_at >= (:snap::date - INTERVAL '12 month')
                      )::float
                    - MAX(tv.aadt) FILTER (
                          WHERE tv.observed_at >= (:snap::date - INTERVAL '36 month')
                            AND tv.observed_at <= (:snap::date - INTERVAL '24 month')
                      )::float
                    ) / NULLIF(
                      MAX(tv.aadt) FILTER (
                          WHERE tv.observed_at >= (:snap::date - INTERVAL '36 month')
                            AND tv.observed_at <= (:snap::date - INTERVAL '24 month')
                      )::float, 0
                    ) AS aadt_growth_3y,
                    AVG(
                        CASE res.stage
                            WHEN 'planned'            THEN 0.10
                            WHEN 'design'             THEN 0.30
                            WHEN 'under_construction' THEN 0.60
                            WHEN 'completed'          THEN 1.00
                            ELSE 0.0
                        END
                    ) AS road_progress
                FROM road_segments rs
                LEFT JOIN traffic_volumes tv ON tv.road_id = rs.id
                LEFT JOIN road_expansion_stages res
                  ON res.road_id = rs.id
                 AND res.occurred_at <= :snap
                WHERE rs.region_code = ANY(:codes)
                GROUP BY rs.region_code
            ),
            names AS (
                SELECT code AS region_code, name FROM admin_areas
                WHERE code = ANY(:codes)
            )
            SELECT
                n.region_code,
                n.name,
                COALESCE(road.road_progress, 0)    AS road_progress,
                COALESCE(pop.pop_avg, 0)           AS population_avg,
                COALESCE(pop.pop_growth_3y, 0)     AS population_growth_3y,
                COALESCE(road.aadt_avg, 0)         AS aadt_avg,
                COALESCE(road.aadt_growth_3y, 0)   AS aadt_growth_3y
            FROM names n
            LEFT JOIN pop  USING (region_code)
            LEFT JOIN road USING (region_code)
            """
        ).bindparams(
            bindparam("snap", value=snap),
            bindparam("codes", value=admin_codes),
        )
        rows = (await self._session.execute(sql)).mappings().all()
        return [
            RegionFeatureVector(
                admin_code=str(r["region_code"]),
                name=r["name"],
                values={
                    "road_progress": float(r["road_progress"] or 0),
                    "population_avg": float(r["population_avg"] or 0),
                    "population_growth_3y": float(r["population_growth_3y"] or 0),
                    "aadt_avg": float(r["aadt_avg"] or 0),
                    "aadt_growth_3y": float(r["aadt_growth_3y"] or 0),
                },
            )
            for r in rows
        ]
