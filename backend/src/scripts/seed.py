"""Seed driver — loads validation cases for Scenarios A, B, and C.

Usage::

    python -m src.scripts.seed                # all scenarios
    python -m src.scripts.seed --scenario c   # scenario C only
    python -m src.scripts.seed --reset        # truncate the seeded tables first

The script is idempotent: re-running without ``--reset`` upserts on the
natural keys defined in the migration (e.g. UNIQUE on
``(brand_id, source_id)`` for stores). ``--reset`` only deletes the tables
this script populates — it never drops the schema.
"""

from __future__ import annotations

import argparse
import asyncio
import math
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.config import get_settings
from src.core.logging import app_logger, configure_logging
from src.models import (
    AdminArea,
    Building,
    LandTransaction,
    OfficialLandPrice,
    PopulationStat,
    Project,
    ProjectStage,
    RoadExpansionStage,
    RoadSegment,
    Store,
    StoreBrand,
    TrafficVolume,
)
from src.scripts.seed_data.admin_areas import ALL_AREAS
from src.scripts.seed_data.projects import PROJECTS
from src.scripts.seed_data.roads import ROADS
from src.scripts.seed_data.stores import (
    BRANDS,
    LAND_PRICE_YEARS_AFTER,
    LAND_PRICE_YEARS_BEFORE,
    STORES,
)

LOGGER = app_logger
"""Module logger — bound at process start by ``configure_logging()``."""


# ─── Geometry helpers (avoid a hard shapely dependency for seed simplicity) ─


def _wkt_point(lon: float, lat: float) -> str:
    return f"SRID=4326;POINT({lon} {lat})"


def _wkt_linestring(coords: Sequence[tuple[float, float]]) -> str:
    body = ", ".join(f"{lon} {lat}" for lon, lat in coords)
    return f"SRID=4326;LINESTRING({body})"


def _wkt_bbox_polygon(centroid: tuple[float, float], half: float) -> str:
    """Build a SRID=4326 MULTIPOLYGON box centered on ``centroid``."""
    lon, lat = centroid
    minlon, maxlon = lon - half, lon + half
    minlat, maxlat = lat - half, lat + half
    ring = (
        f"({minlon} {minlat}, {maxlon} {minlat}, {maxlon} {maxlat}, "
        f"{minlon} {maxlat}, {minlon} {minlat})"
    )
    return f"SRID=4326;MULTIPOLYGON(({ring}))"


# ─── Loaders ────────────────────────────────────────────────────────────────


async def _seed_admin_areas(session: AsyncSession) -> int:
    """Upsert 시·도 → 시·군·구 → 읍·면·동 in dependency order."""
    count = 0
    # Insert sidos first (no parent), then sigungus, then dongs.
    for tier in ("sido", "sigungu", "eupmyeondong"):
        rows = [
            {
                "code": a["code"],
                "name": a["name"],
                "level": a["level"],
                "parent_code": a["parent_code"],
                "centroid": (
                    _wkt_point(*a["centroid"]) if a["centroid"] else None
                ),
            }
            for a in ALL_AREAS
            if a["level"] == tier
        ]
        for row in rows:
            stmt = pg_insert(AdminArea).values(**row).on_conflict_do_update(
                index_elements=[AdminArea.code],
                set_={k: row[k] for k in ("name", "level", "parent_code", "centroid")},
            )
            await session.execute(stmt)
            count += 1
    return count


async def _seed_projects(session: AsyncSession) -> int:
    count = 0
    for p in PROJECTS:
        stmt = (
            pg_insert(Project)
            .values(
                name=p["name"],
                project_type=p["project_type"],
                region_code=p["region_code"],
                geometry=_wkt_bbox_polygon(p["centroid"], p["bbox_half_size_deg"]),
                centroid=_wkt_point(*p["centroid"]),
                area_ha=p["area_ha"],
                expected_compensation_billion_krw=p["expected_compensation_billion_krw"],
                planned_announcement_date=p["planned_announcement_date"],
                planned_completion_date=p["planned_completion_date"],
                description=p["description"],
                source=p["source"],
                raw_data={"seed": True},
            )
            .on_conflict_do_update(
                constraint="uq_projects_name_type",
                set_={
                    "region_code": p["region_code"],
                    "geometry": _wkt_bbox_polygon(p["centroid"], p["bbox_half_size_deg"]),
                    "centroid": _wkt_point(*p["centroid"]),
                    "area_ha": p["area_ha"],
                    "expected_compensation_billion_krw": p[
                        "expected_compensation_billion_krw"
                    ],
                    "planned_announcement_date": p["planned_announcement_date"],
                    "planned_completion_date": p["planned_completion_date"],
                    "description": p["description"],
                    "source": p["source"],
                },
            )
            .returning(Project.id)
        )
        result = await session.execute(stmt)
        project_id = result.scalar_one()
        count += 1

        for idx, stg in enumerate(p["stages"], start=1):
            await session.execute(
                pg_insert(ProjectStage)
                .values(
                    project_id=project_id,
                    stage=stg["stage"],
                    occurred_at=stg["occurred_at"],
                    sequence_no=idx,
                    note=stg.get("note"),
                    source=p["source"],
                )
                .on_conflict_do_nothing(
                    constraint="uq_project_stages_project_stage_date"
                )
            )
    return count


async def _seed_roads(session: AsyncSession) -> tuple[int, int, int]:
    """Returns (roads, traffic_rows, population_rows)."""
    n_roads = n_traffic = n_pop = 0
    for r in ROADS:
        stmt = (
            pg_insert(RoadSegment)
            .values(
                name=r["name"],
                route_no=r["route_no"],
                region_code=r["region_code"],
                geometry=_wkt_linestring(r["line"]),
                length_m=r["length_m"],
                description=r["description"],
                source=r["source"],
                raw_data={"seed": True},
            )
            .on_conflict_do_update(
                constraint="uq_road_segments_name_route",
                set_={
                    "geometry": _wkt_linestring(r["line"]),
                    "length_m": r["length_m"],
                    "description": r["description"],
                    "source": r["source"],
                },
            )
            .returning(RoadSegment.id)
        )
        road_id = (await session.execute(stmt)).scalar_one()
        n_roads += 1

        for stg in r["stages"]:
            await session.execute(
                pg_insert(RoadExpansionStage)
                .values(
                    road_id=road_id,
                    stage=stg["stage"],
                    occurred_at=stg["occurred_at"],
                    lanes_before=stg.get("lanes_before"),
                    lanes_after=stg.get("lanes_after"),
                    source=r["source"],
                )
                .on_conflict_do_nothing(
                    constraint="uq_road_expansion_stages_road_stage_date"
                )
            )

        # 7 years of monthly traffic + abutting population
        n_traffic += await _seed_traffic_series(session, road_id=road_id, road=r)
        n_pop += await _seed_population_series(session, road=r)

    return n_roads, n_traffic, n_pop


async def _seed_traffic_series(
    session: AsyncSession,
    *,
    road_id: int,
    road: Mapping[str, Any],
) -> int:
    """Generate 7 years (2018-01 .. 2024-12) of monthly AADT for ``road_id``.

    The series ramps after ``completed`` stage to mimic the road expansion
    effect (so Scenario B regression has signal).
    """
    completed_stage = next(
        (s for s in road["stages"] if s["stage"] == "completed"),
        None,
    )
    completed_at = completed_stage["occurred_at"] if completed_stage else None
    base_aadt = 12_000

    inserted = 0
    cur = date(2018, 1, 1)
    while cur < date(2025, 1, 1):
        # Slow secular growth + post-expansion bump.
        years_elapsed = (cur - date(2018, 1, 1)).days / 365.25
        secular = 1.0 + 0.015 * years_elapsed
        bump = 0.0
        if completed_at and cur >= completed_at:
            months_after = (cur - completed_at).days / 30
            bump = 0.18 * (1 - math.exp(-months_after / 12))
        aadt = int(base_aadt * (secular + bump))
        peak = int(aadt * 0.11)

        await session.execute(
            pg_insert(TrafficVolume)
            .values(
                road_id=road_id,
                observed_at=cur,
                aadt=aadt,
                peak_hour_volume=peak,
                heavy_vehicle_pct=8.0,
                source="seed:synthetic",
                raw_data={"synthetic": True, "model": "seed_series_v1"},
            )
            .on_conflict_do_nothing(
                constraint="uq_traffic_volumes_road_observed_at"
            )
        )
        inserted += 1
        # advance one month
        if cur.month == 12:
            cur = cur.replace(year=cur.year + 1, month=1)
        else:
            cur = cur.replace(month=cur.month + 1)
    return inserted


async def _seed_population_series(
    session: AsyncSession, *, road: Mapping[str, Any]
) -> int:
    """Generate 7 years of monthly population for each abutting 행정동."""
    inserted = 0
    base_pop = {code: 22_000 + (hash(code) % 12_000) for code in road["abutting_admin_codes"]}
    cur = date(2018, 1, 1)
    while cur < date(2025, 1, 1):
        for code, base in base_pop.items():
            years_elapsed = (cur - date(2018, 1, 1)).days / 365.25
            pop = int(base * (1.0 + 0.012 * years_elapsed))
            households = int(pop / 2.55)
            await session.execute(
                pg_insert(PopulationStat)
                .values(
                    region_code=code,
                    observed_at=cur,
                    total_population=pop,
                    male_population=int(pop * 0.503),
                    female_population=pop - int(pop * 0.503),
                    household_count=households,
                    avg_age=42.5,
                    source="seed:synthetic",
                )
                .on_conflict_do_nothing(
                    constraint="uq_population_stats_region_observed_at"
                )
            )
            inserted += 1
        if cur.month == 12:
            cur = cur.replace(year=cur.year + 1, month=1)
        else:
            cur = cur.replace(month=cur.month + 1)
    return inserted


async def _seed_brands(session: AsyncSession) -> dict[str, int]:
    """Returns name → brand_id for downstream use."""
    name_to_id: dict[str, int] = {}
    for b in BRANDS:
        stmt = (
            pg_insert(StoreBrand)
            .values(
                name=b["name"],
                name_en=b["name_en"],
                category=b["category"],
                country=b["country"],
            )
            .on_conflict_do_update(
                constraint="uq_store_brands_name",
                set_={"name_en": b["name_en"], "category": b["category"]},
            )
            .returning(StoreBrand.id)
        )
        name_to_id[b["name"]] = (await session.execute(stmt)).scalar_one()
    return name_to_id


def _load_verified_coords() -> dict[str, tuple[float, float]]:
    """Read the Naver-verified coordinate cache, if present.

    Returns ``{source_id: (lng, lat)}``. Missing file or missing keys
    are not errors — the seed falls back to the placeholder coordinates
    that ship in :mod:`stores`.
    """
    import json  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    path = Path(__file__).parent / "seed_data" / "store_coords_verified.json"
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    out: dict[str, tuple[float, float]] = {}
    for source_id, record in raw.items():
        if (
            isinstance(record, dict)
            and record.get("status") == "ok"
            and "latitude" in record
            and "longitude" in record
        ):
            out[source_id] = (float(record["longitude"]), float(record["latitude"]))
    return out


def _canonical_pnu(raw: str) -> str:
    """Strip hyphens from a PNU. The seed data is human-readable
    (``4128010500-1-0001-0000``) but the DB column is ``VARCHAR(19)``,
    so we collapse to the canonical 19-digit form on insert."""
    return raw.replace("-", "")


async def _seed_buildings_and_stores(
    session: AsyncSession,
    brand_ids: dict[str, int],
) -> tuple[int, int, int, int]:
    """Returns (buildings, stores, land_prices, halo_transactions)."""
    n_buildings = n_stores = n_prices = n_tx = 0

    verified_coords = _load_verified_coords()
    if verified_coords:
        LOGGER.info(
            "seed_using_verified_coords", count=len(verified_coords),
        )

    for s in STORES:
        # Verified Naver coordinates take precedence over placeholders.
        location = verified_coords.get(s["source_id"], s["location"])
        # Normalise PNU once — DB column is VARCHAR(19), seed text uses
        # human-readable hyphens.
        pnu = _canonical_pnu(s["pnu"])
        # Building (one per PNU)
        await session.execute(
            pg_insert(Building)
            .values(
                pnu=pnu,
                address=s["address"],
                region_code=s["region_code"],
                parcel_area_m2=s["land_area_m2"],
                building_area_m2=s["building_area_m2"],
                total_floor_area_m2=s["building_area_m2"] * 1.4,
                floors_above=2,
                floors_below=0,
                use_type=s["use_type"],
                structure=s["structure"],
                approval_date=s["construction_approval_date"],
                source="seed:validation",
            )
            .on_conflict_do_update(
                index_elements=[Building.pnu],
                set_={
                    "address": s["address"],
                    "use_type": s["use_type"],
                    "approval_date": s["construction_approval_date"],
                },
            )
        )
        n_buildings += 1

        # Store
        stmt = (
            pg_insert(Store)
            .values(
                brand_id=brand_ids[s["brand"]],
                source_id=s["source_id"],
                source_url=None,
                name=s["name"],
                address=s["address"],
                region_code=s["region_code"],
                location=_wkt_point(*location),
                pnu=pnu,
                store_type=s["store_type"],
                purchase_date=s["purchase_date"],
                construction_approval_date=s["construction_approval_date"],
                opened_at=s["opened_at"],
                land_area_m2=s["land_area_m2"],
                building_area_m2=s["building_area_m2"],
                raw_data={
                    "seed": True,
                    "coords_verified": s["source_id"] in verified_coords,
                },
            )
            .on_conflict_do_update(
                constraint="uq_stores_brand_source_id",
                set_={
                    "name": s["name"],
                    "address": s["address"],
                    "location": _wkt_point(*location),
                    "pnu": pnu,
                    "store_type": s["store_type"],
                    "opened_at": s["opened_at"],
                    "land_area_m2": s["land_area_m2"],
                    "building_area_m2": s["building_area_m2"],
                },
            )
            .returning(Store.id)
        )
        store_id = (await session.execute(stmt)).scalar_one()
        n_stores += 1

        # 5-year price series — relative to opened_at
        opened_year = s["opened_at"].year
        for offset in range(-LAND_PRICE_YEARS_BEFORE, LAND_PRICE_YEARS_AFTER + 1):
            year = opened_year + offset
            price = int(s["base_price_per_m2"] * (1 + s["annual_growth"]) ** offset)
            change = (
                None
                if offset == -LAND_PRICE_YEARS_BEFORE
                else round(s["annual_growth"] * 100, 4)
            )
            await session.execute(
                pg_insert(OfficialLandPrice)
                .values(
                    pnu=pnu,
                    year=year,
                    price_per_m2=price,
                    change_rate=change,
                    source="seed:synthetic",
                )
                .on_conflict_do_update(
                    constraint="uq_official_land_prices_pnu_year",
                    set_={"price_per_m2": price, "change_rate": change},
                )
            )
            n_prices += 1

        # Halo transactions for impact analysis: 6 nearby parcels, 3 pre / 3 post.
        # Use the resolved (possibly verified) location so halo rows scatter
        # around the real coordinates.
        n_tx += await _seed_halo_transactions(
            session, store=s, store_id=store_id, location=location,
        )

    return n_buildings, n_stores, n_prices, n_tx


async def _seed_halo_transactions(
    session: AsyncSession,
    *,
    store: Mapping[str, Any],
    store_id: int,
    location: tuple[float, float] | None = None,
) -> int:
    """Insert 6 land transactions in a ring around the store.

    Three are dated 18 months before opening (pre window) and three 18
    months after (post window) so Scenario C halo analysis has rows.
    """
    inserted = 0
    open_date = store["opened_at"]
    pre_date = open_date - timedelta(days=540)
    post_date = open_date + timedelta(days=540)
    base_lon, base_lat = location or store["location"]

    for offset_idx, (lon_off, lat_off) in enumerate(
        [(0.0008, 0.0), (-0.0008, 0.0), (0.0, 0.0008),
         (0.0, -0.0008), (0.0006, 0.0006), (-0.0006, -0.0006)]
    ):
        is_post = offset_idx >= 3
        contract_date = post_date if is_post else pre_date
        deal = int(
            store["base_price_per_m2"]
            * (1 + store["annual_growth"]) ** (-2 if not is_post else 1)
            * 280  # m2 typical
            * (1.18 if is_post else 1.0)
        )
        source_id = f"seed-halo-{store_id}-{offset_idx}"
        await session.execute(
            pg_insert(LandTransaction)
            .values(
                source_id=source_id,
                source="seed:synthetic",
                region_code=store["region_code"],
                pnu=None,
                address=store["address"],
                location=_wkt_point(base_lon + lon_off, base_lat + lat_off),
                transaction_type="land",
                contract_date=contract_date,
                deal_amount_krw=deal,
                area_m2=280.0,
                use_district="제2종일반주거지역",
                raw_data={"seed": True, "store_id": store_id, "offset_idx": offset_idx},
            )
            .on_conflict_do_nothing(
                constraint="uq_land_transactions_source_id"
            )
        )
        inserted += 1
    return inserted


# ─── Reset ──────────────────────────────────────────────────────────────────


_TABLES_TO_RESET: list[str] = [
    "store_impact_analysis",
    "candidate_lands",
    "store_features",
    "official_land_prices",
    "stores",
    "store_brands",
    "buildings",
    "land_transactions",
    "traffic_volumes",
    "road_expansion_stages",
    "road_segments",
    "population_stats",
    "project_stages",
    "projects",
    "admin_areas",
]


async def _reset(session: AsyncSession) -> None:
    """Truncate seeded tables. Cascades through FKs."""
    LOGGER.warning("seed_reset", tables=_TABLES_TO_RESET)
    for tbl in _TABLES_TO_RESET:
        await session.execute(text(f"TRUNCATE TABLE {tbl} RESTART IDENTITY CASCADE"))


# ─── Main entrypoint ───────────────────────────────────────────────────────


async def run(scenario: str, reset: bool, dry_run: bool) -> dict[str, int]:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, future=True)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    counts: dict[str, int] = {}
    async with Session() as session, session.begin():
        if reset:
            await _reset(session)

        counts["admin_areas"] = await _seed_admin_areas(session)

        if scenario in ("a", "all"):
            counts["projects"] = await _seed_projects(session)

        if scenario in ("b", "all"):
            roads_n, traffic_n, pop_n = await _seed_roads(session)
            counts["roads"] = roads_n
            counts["traffic_rows"] = traffic_n
            counts["population_rows"] = pop_n

        if scenario in ("c", "all"):
            brand_ids = await _seed_brands(session)
            counts["brands"] = len(brand_ids)
            bld, sto, prc, tx = await _seed_buildings_and_stores(
                session, brand_ids
            )
            counts["buildings"] = bld
            counts["stores"] = sto
            counts["land_prices"] = prc
            counts["halo_transactions"] = tx

        if dry_run:
            LOGGER.info("seed_dry_run", counts=counts)
            await session.rollback()
            return counts

    await engine.dispose()
    LOGGER.info("seed_complete", scenario=scenario, counts=counts)
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed validation data for Scenarios A/B/C."
    )
    parser.add_argument(
        "--scenario", choices=["a", "b", "c", "all"], default="all",
        help="Which scenario to seed. Default: all.",
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Truncate seeded tables first (CASCADE). Destructive.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Run inside a transaction and roll back. No DB writes persist.",
    )
    args = parser.parse_args()

    configure_logging()
    started = datetime.now(tz=UTC)
    counts = asyncio.run(run(args.scenario, args.reset, args.dry_run))
    elapsed = (datetime.now(tz=UTC) - started).total_seconds()
    print(
        f"Seed complete in {elapsed:.1f}s. Counts: {counts}"
    )


# Quiet unused-import grumbles when not all loaders are reached.
_ = (Iterable, select, delete)


if __name__ == "__main__":
    main()
