"""Scenario C — feature engineering.

Three extraction modes:

* :meth:`FeatureExtractor.extract_for_store` — used to build the training set
  (joins live store rows with population/traffic/competitor counts).
* :meth:`FeatureExtractor.extract_for_pnu` — used at inference time when
  the candidate parcel has a row in ``buildings``.
* :meth:`FeatureExtractor.extract_for_location` — used for arbitrary
  coordinates (no PNU yet); falls back to admin-area features only.

Phase 1 ships the PostGIS-driven path with the variables that the seed
data covers. Catalysts (호재 변수) read from cached Scenario A/B results
when available and default to zero otherwise — keeping the model usable
before those analyses run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import numpy as np
import numpy.typing as npt
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

# ─── Feature catalog ───────────────────────────────────────────────────────


# Names mirror what the XGBoost model was trained on. Order matters and is
# the single source of truth for serialization.
FEATURE_NAMES: list[str] = [
    # Real-estate (8)
    "land_area_m2",
    "building_area_m2",
    "floor_area_ratio",
    "land_price_per_m2",
    "land_price_yoy",
    "land_price_5y_growth",
    "is_commercial_zone",
    "is_corner_lot",
    # Surroundings (8)
    "population_within_1km",
    "population_within_3km",
    "household_count_within_1km",
    "competitor_count_within_1km",
    "competitor_count_within_500m",
    "same_brand_count_within_3km",
    "transit_score_500m",
    "office_count_within_1km",
    # Catalysts / 호재 (5)
    "nearby_road_expansion",
    "nearby_new_town",
    "subway_extension_planned",
    "population_growth_3y_pct",
    "transaction_count_growth_3y",
    # Geometry / location (4)
    "distance_to_nearest_road_m",
    "aadt_nearest_road",
    "elevation_relative",
    "drive_thru_accessible",
]


@dataclass(slots=True)
class FeatureVector:
    """One feature row ready for inference / training."""

    pnu: str | None
    snapshot_date: date
    values: dict[str, float] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_array(self) -> npt.NDArray[np.float64]:
        """Return the feature row in canonical ``FEATURE_NAMES`` order."""
        return np.array(
            [float(self.values.get(name, 0.0)) for name in FEATURE_NAMES],
            dtype=np.float64,
        )


# ─── Extractor ─────────────────────────────────────────────────────────────


class FeatureExtractor:
    """Computes feature vectors from the DB.

    Heavy aggregations are pushed into PostgreSQL via ``ST_DWithin`` so the
    Python-side cost is small even for thousands of candidates.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def extract_for_store(
        self,
        store_id: int,
        *,
        snapshot_date: date | None = None,
    ) -> FeatureVector | None:
        """Build the training feature row for one existing store."""
        store = await self._fetch_store(store_id)
        if store is None:
            return None
        snap = snapshot_date or store["opened_at"] or date.today()
        return await self._extract_at(
            pnu=store["pnu"],
            lat=store["lat"],
            lng=store["lng"],
            region_code=store["region_code"],
            snapshot_date=snap,
            owner_store_id=store_id,
            land_area_m2=store["land_area_m2"],
            building_area_m2=store["building_area_m2"],
            brand_id=store["brand_id"],
        )

    async def extract_for_pnu(
        self,
        pnu: str,
        snapshot_date: date | None = None,
    ) -> FeatureVector | None:
        building = await self._fetch_building(pnu)
        if building is None:
            return None
        snap = snapshot_date or date.today()
        return await self._extract_at(
            pnu=pnu,
            lat=building["lat"],
            lng=building["lng"],
            region_code=building["region_code"],
            snapshot_date=snap,
            owner_store_id=None,
            land_area_m2=building["parcel_area_m2"] or 0.0,
            building_area_m2=building["building_area_m2"] or 0.0,
            brand_id=None,
        )

    async def extract_for_location(
        self,
        *,
        lat: float,
        lng: float,
        snapshot_date: date | None = None,
    ) -> FeatureVector:
        snap = snapshot_date or date.today()
        return await self._extract_at(
            pnu=None,
            lat=lat,
            lng=lng,
            region_code=None,
            snapshot_date=snap,
            owner_store_id=None,
            land_area_m2=0.0,
            building_area_m2=0.0,
            brand_id=None,
        )

    # ─── Internal — DB lookups ──────────────────────────────────────────

    async def _fetch_store(self, store_id: int) -> dict[str, Any] | None:
        sql = text(
            """
            SELECT
                s.id, s.brand_id, s.pnu, s.region_code, s.opened_at,
                s.land_area_m2, s.building_area_m2,
                ST_X(s.location) AS lng, ST_Y(s.location) AS lat
            FROM stores s
            WHERE s.id = :store_id
            """
        ).bindparams(bindparam("store_id", value=store_id))
        result = await self._session.execute(sql)
        row = result.mappings().first()
        return dict(row) if row else None

    async def _fetch_building(self, pnu: str) -> dict[str, Any] | None:
        sql = text(
            """
            SELECT
                pnu, region_code, parcel_area_m2, building_area_m2,
                ST_X(ST_Centroid(geometry)) AS lng,
                ST_Y(ST_Centroid(geometry)) AS lat
            FROM buildings
            WHERE pnu = :pnu
            """
        ).bindparams(bindparam("pnu", value=pnu))
        row = (await self._session.execute(sql)).mappings().first()
        return dict(row) if row else None

    async def _extract_at(
        self,
        *,
        pnu: str | None,
        lat: float | None,
        lng: float | None,
        region_code: str | None,
        snapshot_date: date,
        owner_store_id: int | None,
        land_area_m2: float,
        building_area_m2: float,
        brand_id: int | None,
    ) -> FeatureVector:
        values: dict[str, float] = dict.fromkeys(FEATURE_NAMES, 0.0)

        # ─── Real-estate ─────────────────────────────────────────────
        values["land_area_m2"] = float(land_area_m2 or 0.0)
        values["building_area_m2"] = float(building_area_m2 or 0.0)
        if land_area_m2:
            values["floor_area_ratio"] = round(
                float(building_area_m2 or 0.0) / float(land_area_m2), 4
            )

        if pnu:
            land_prices = await self._fetch_land_prices(pnu)
            if land_prices:
                latest = land_prices[-1]
                earliest = land_prices[0]
                values["land_price_per_m2"] = float(latest["price"])
                if len(land_prices) >= 2 and land_prices[-2]["price"]:
                    values["land_price_yoy"] = round(
                        (latest["price"] - land_prices[-2]["price"])
                        / land_prices[-2]["price"], 4
                    )
                if earliest["price"]:
                    values["land_price_5y_growth"] = round(
                        (latest["price"] - earliest["price"]) / earliest["price"], 4
                    )

        # ─── Surroundings (PostGIS aggregations) ─────────────────────
        if lat is not None and lng is not None:
            surroundings = await self._fetch_surroundings(
                lat=lat, lng=lng,
                snapshot_date=snapshot_date,
                exclude_store_id=owner_store_id,
                same_brand_id=brand_id,
            )
            values.update(surroundings)

            road_features = await self._fetch_nearest_road(lat=lat, lng=lng)
            values.update(road_features)

        # ─── Catalysts ────────────────────────────────────────────────
        if region_code:
            values.update(await self._fetch_catalysts(region_code, snapshot_date))

        # Drive-thru accessibility heuristic — has a building footprint,
        # building-area-ratio < 0.7, AND distance to nearest 4-lane road < 200m.
        if (
            building_area_m2 and land_area_m2
            and (building_area_m2 / land_area_m2) < 0.7
            and values.get("distance_to_nearest_road_m", 9999) < 200
        ):
            values["drive_thru_accessible"] = 1.0

        return FeatureVector(
            pnu=pnu,
            snapshot_date=snapshot_date,
            values=values,
            extra={"region_code": region_code, "lat": lat, "lng": lng},
        )

    async def _fetch_land_prices(self, pnu: str) -> list[dict[str, Any]]:
        sql = text(
            """
            SELECT year, price_per_m2 AS price
            FROM official_land_prices
            WHERE pnu = :pnu
            ORDER BY year
            """
        ).bindparams(bindparam("pnu", value=pnu))
        rows = (await self._session.execute(sql)).mappings().all()
        return [dict(r) for r in rows]

    async def _fetch_surroundings(
        self,
        *,
        lat: float,
        lng: float,
        snapshot_date: date,
        exclude_store_id: int | None,
        same_brand_id: int | None,
    ) -> dict[str, float]:
        # One round-trip computes every PostGIS aggregation we need.
        sql = text(
            """
            WITH q AS (
                SELECT ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography AS geog
            ),
            pop AS (
                SELECT
                    SUM(ps.total_population)
                        FILTER (WHERE ST_DWithin(aa.centroid::geography, q.geog, 1000))
                        AS pop_1km,
                    SUM(ps.total_population)
                        FILTER (WHERE ST_DWithin(aa.centroid::geography, q.geog, 3000))
                        AS pop_3km,
                    SUM(ps.household_count)
                        FILTER (WHERE ST_DWithin(aa.centroid::geography, q.geog, 1000))
                        AS hh_1km
                FROM admin_areas aa
                JOIN population_stats ps
                  ON ps.region_code = aa.code
                 AND ps.observed_at <= :snapshot_date
                 AND ps.observed_at >= (:snapshot_date::date - INTERVAL '90 day'),
                     q
                WHERE aa.centroid IS NOT NULL
            ),
            comp AS (
                SELECT
                    COUNT(*) FILTER (
                        WHERE ST_DWithin(s.location::geography, q.geog, 1000)
                    ) AS comp_1km,
                    COUNT(*) FILTER (
                        WHERE ST_DWithin(s.location::geography, q.geog, 500)
                    ) AS comp_500m,
                    COUNT(*) FILTER (
                        WHERE ST_DWithin(s.location::geography, q.geog, 3000)
                          AND s.brand_id = :same_brand_id
                    ) AS same_brand_3km
                FROM stores s, q
                WHERE s.location IS NOT NULL
                  AND s.id IS DISTINCT FROM :exclude_store_id
            )
            SELECT
                COALESCE(pop.pop_1km, 0)         AS pop_1km,
                COALESCE(pop.pop_3km, 0)         AS pop_3km,
                COALESCE(pop.hh_1km, 0)          AS hh_1km,
                COALESCE(comp.comp_1km, 0)       AS comp_1km,
                COALESCE(comp.comp_500m, 0)      AS comp_500m,
                COALESCE(comp.same_brand_3km, 0) AS same_brand_3km
            FROM pop, comp
            """
        ).bindparams(
            bindparam("lat", value=lat),
            bindparam("lng", value=lng),
            bindparam("snapshot_date", value=snapshot_date),
            bindparam("exclude_store_id", value=exclude_store_id),
            bindparam("same_brand_id", value=same_brand_id),
        )
        row = (await self._session.execute(sql)).mappings().first()
        if not row:
            return {}
        return {
            "population_within_1km": float(row["pop_1km"] or 0),
            "population_within_3km": float(row["pop_3km"] or 0),
            "household_count_within_1km": float(row["hh_1km"] or 0),
            "competitor_count_within_1km": float(row["comp_1km"] or 0),
            "competitor_count_within_500m": float(row["comp_500m"] or 0),
            "same_brand_count_within_3km": float(row["same_brand_3km"] or 0),
        }

    async def _fetch_nearest_road(
        self, *, lat: float, lng: float
    ) -> dict[str, float]:
        sql = text(
            """
            SELECT
                rs.id AS road_id,
                ST_Distance(
                    rs.geometry::geography,
                    ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography
                ) AS distance_m,
                (
                    SELECT AVG(aadt)::int
                    FROM traffic_volumes tv
                    WHERE tv.road_id = rs.id
                      AND tv.observed_at >= (CURRENT_DATE - INTERVAL '12 month')
                ) AS avg_aadt
            FROM road_segments rs
            WHERE rs.geometry IS NOT NULL
            ORDER BY rs.geometry <-> ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)
            LIMIT 1
            """
        ).bindparams(
            bindparam("lat", value=lat),
            bindparam("lng", value=lng),
        )
        row = (await self._session.execute(sql)).mappings().first()
        if not row:
            return {"distance_to_nearest_road_m": 9999.0, "aadt_nearest_road": 0.0}
        return {
            "distance_to_nearest_road_m": float(row["distance_m"] or 9999.0),
            "aadt_nearest_road": float(row["avg_aadt"] or 0),
        }

    async def _fetch_catalysts(
        self, region_code: str, snapshot_date: date
    ) -> dict[str, float]:
        """Catalyst variables — read from precomputed tables if present.

        Values default to zero so the model is still trainable in
        environments where Scenario A/B haven't been run yet.
        """
        # Population growth over the last 3 years (uses the same admin area).
        sql_growth = text(
            """
            WITH bounds AS (
                SELECT
                    MIN(total_population) FILTER (
                        WHERE observed_at >= (:snapshot_date::date - INTERVAL '36 month')
                          AND observed_at <= (:snapshot_date::date - INTERVAL '30 month')
                    ) AS pop_3y_ago,
                    MAX(total_population) FILTER (
                        WHERE observed_at >= (:snapshot_date::date - INTERVAL '6 month')
                          AND observed_at <= :snapshot_date
                    ) AS pop_now
                FROM population_stats
                WHERE region_code = :region_code
            )
            SELECT pop_3y_ago, pop_now FROM bounds
            """
        ).bindparams(
            bindparam("region_code", value=region_code),
            bindparam("snapshot_date", value=snapshot_date),
        )
        row = (await self._session.execute(sql_growth)).mappings().first()
        growth = 0.0
        if row and row["pop_3y_ago"] and row["pop_now"]:
            growth = round(
                (float(row["pop_now"]) - float(row["pop_3y_ago"]))
                / float(row["pop_3y_ago"]),
                4,
            )

        # Nearby road expansion: count of road_segments with a 'completed'
        # stage within the surrounding sigungu in the last 3 years.
        sql_road = text(
            """
            SELECT COUNT(*) AS n
            FROM road_segments rs
            JOIN road_expansion_stages res ON res.road_id = rs.id
            WHERE rs.region_code = :region_code
              AND res.stage = 'completed'
              AND res.occurred_at >= (:snapshot_date::date - INTERVAL '36 month')
            """
        ).bindparams(
            bindparam("region_code", value=region_code),
            bindparam("snapshot_date", value=snapshot_date),
        )
        road_n = (await self._session.execute(sql_road)).scalar_one_or_none() or 0

        # Nearby new town: any project in same sigungu with a 'designated'
        # stage in the trailing 5 years.
        sql_nt = text(
            """
            SELECT COUNT(*) AS n
            FROM projects p
            JOIN project_stages ps ON ps.project_id = p.id
            WHERE p.region_code = :region_code
              AND ps.stage IN ('designated', 'announced')
              AND ps.occurred_at >= (:snapshot_date::date - INTERVAL '60 month')
            """
        ).bindparams(
            bindparam("region_code", value=region_code),
            bindparam("snapshot_date", value=snapshot_date),
        )
        nt_n = (await self._session.execute(sql_nt)).scalar_one_or_none() or 0

        # Transaction count growth — short-window proxy.
        cutoff = snapshot_date - timedelta(days=30 * 36)
        sql_tx = text(
            """
            SELECT
                COUNT(*) FILTER (
                    WHERE contract_date >= (:cutoff::date)
                      AND contract_date <  (:cutoff::date + INTERVAL '12 month')
                ) AS old_n,
                COUNT(*) FILTER (
                    WHERE contract_date >= (:snapshot_date::date - INTERVAL '12 month')
                      AND contract_date <= :snapshot_date
                ) AS new_n
            FROM land_transactions
            WHERE region_code = :region_code
            """
        ).bindparams(
            bindparam("region_code", value=region_code),
            bindparam("cutoff", value=cutoff),
            bindparam("snapshot_date", value=snapshot_date),
        )
        row_tx = (await self._session.execute(sql_tx)).mappings().first()
        tx_growth = 0.0
        if row_tx and row_tx["old_n"]:
            tx_growth = round(
                (float(row_tx["new_n"]) - float(row_tx["old_n"]))
                / float(row_tx["old_n"]),
                4,
            )

        return {
            "nearby_road_expansion": float(road_n),
            "nearby_new_town": float(nt_n),
            "subway_extension_planned": 0.0,  # Phase 2: parse 국토부 RFP feed.
            "population_growth_3y_pct": growth,
            "transaction_count_growth_3y": tx_growth,
        }
