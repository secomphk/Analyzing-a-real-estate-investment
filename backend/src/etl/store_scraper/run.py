"""CLI entry — runs one or every concrete scraper end-to-end.

Usage::

    python -m src.etl.store_scraper.run --brand all
    python -m src.etl.store_scraper.run --brand starbucks --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Iterable
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.config import get_settings
from src.core.logging import app_logger, configure_logging
from src.etl.common import check_kill_switch, log_row_error
from src.etl.store_scraper.base import BaseStoreScraper, StoreData
from src.etl.store_scraper.mcdonalds import McDonaldsScraper
from src.etl.store_scraper.starbucks import StarbucksScraper
from src.models import Store, StoreBrand

LOGGER = app_logger
PIPELINE_NAME = "store_scraper"

SCRAPERS: dict[str, type[BaseStoreScraper]] = {
    "starbucks": StarbucksScraper,
    "mcdonalds": McDonaldsScraper,
}


async def _ensure_brand(session: AsyncSession, name: str, *, category: str) -> int:
    """Look up or insert the brand row, return its id."""
    result = await session.execute(
        select(StoreBrand.id).where(StoreBrand.name == name)
    )
    row_id = result.scalar_one_or_none()
    if row_id is not None:
        return int(row_id)
    insert_stmt = (
        pg_insert(StoreBrand)
        .values(name=name, category=category, country="KR")
        .on_conflict_do_update(
            constraint="uq_store_brands_name",
            set_={"category": category},
        )
        .returning(StoreBrand.id)
    )
    return int((await session.execute(insert_stmt)).scalar_one())


async def upsert_stores(
    session: AsyncSession,
    *,
    brand_id: int,
    rows: Iterable[StoreData],
    dry_run: bool = False,
) -> int:
    """UPSERT stores keyed on ``(brand_id, source_id)``."""
    count = 0
    for s in rows:
        try:
            payload: dict[str, Any] = {
                "brand_id": brand_id,
                "source_id": s.source_id,
                "source_url": s.source_url,
                "name": s.name,
                "address": s.address,
                "location": (
                    f"SRID=4326;POINT({s.longitude} {s.latitude})"
                    if s.latitude and s.longitude
                    else None
                ),
                "store_type": s.store_type,
                "opened_at": s.opened_at,
                "raw_data": s.raw,
            }
            stmt = (
                pg_insert(Store)
                .values(**payload)
                .on_conflict_do_update(
                    constraint="uq_stores_brand_source_id",
                    set_={
                        "name": payload["name"],
                        "address": payload["address"],
                        "location": payload["location"],
                        "store_type": payload["store_type"],
                        "raw_data": payload["raw_data"],
                    },
                )
            )
            if not dry_run:
                await session.execute(stmt)
            count += 1
        except Exception as exc:  # noqa: BLE001
            log_row_error(pipeline=PIPELINE_NAME, row={"source_id": s.source_id}, error=str(exc))
    return count


async def _run_one(brand_key: str, *, dry_run: bool) -> dict[str, int]:
    check_kill_switch()
    settings = get_settings()
    cls = SCRAPERS[brand_key]
    async with cls() as scraper:
        stores = await scraper.fetch_all_stores()

    LOGGER.info(
        "scraper_fetched", brand=cls.brand_name, count=len(stores),
        dt_count=sum(1 for s in stores if s.store_type == "DT"),
    )

    if dry_run:
        return {"fetched": len(stores), "upserted": 0}

    engine = create_async_engine(settings.database_url, future=True)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as session, session.begin():
            brand_id = await _ensure_brand(session, cls.brand_name, category="cafe")
            upserted = await upsert_stores(
                session, brand_id=brand_id, rows=stores, dry_run=False
            )
    finally:
        await engine.dispose()
    return {"fetched": len(stores), "upserted": upserted}


async def _run(brand: str, *, dry_run: bool) -> dict[str, dict[str, int]]:
    if brand == "all":
        brands = list(SCRAPERS.keys())
    elif brand in SCRAPERS:
        brands = [brand]
    else:
        raise SystemExit(
            f"Unknown brand: {brand}. Choose from: {sorted(SCRAPERS.keys())} or 'all'."
        )
    out: dict[str, dict[str, int]] = {}
    for b in brands:
        out[b] = await _run_one(b, dry_run=dry_run)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Store catalog scraper runner.")
    parser.add_argument(
        "--brand", default="all",
        help=f"One of: {', '.join(SCRAPERS)} or 'all'.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    configure_logging()
    summary = asyncio.run(_run(args.brand, dry_run=args.dry_run))
    print(f"Store scraper: {summary}")  # noqa: T201


if __name__ == "__main__":
    main()
