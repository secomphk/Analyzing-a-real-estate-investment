"""개별공시지가 ETL — Scenario C 시계열 입력.

Annual loader: pulls land prices for a year + optional PNU list, computes
the YoY change rate where the prior year exists.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Iterable
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.config import get_settings
from src.core.logging import app_logger, configure_logging
from src.etl.common import (
    USER_AGENT_DEFAULT,
    check_kill_switch,
    http_get_with_retry,
    log_row_error,
)
from src.models import OfficialLandPrice

LOGGER = app_logger
PIPELINE_NAME = "land_price"

DEFAULT_BASE_URL = "https://api.vworld.kr/ned/data/getIndvdLandPriceAttr"


def _parse_int(value: Any) -> int:
    if value is None or value == "":
        return 0
    return int(str(value).replace(",", "").strip())


def normalize_row(raw: dict[str, Any], *, year: int) -> dict[str, Any] | None:
    pnu = raw.get("pnu") or raw.get("PNU") or raw.get("pnuCode")
    price_raw = (
        raw.get("indvdLandPrice")
        or raw.get("price")
        or raw.get("officialPrice")
        or raw.get("pblntfPclnd")
    )
    if not pnu or price_raw is None:
        return None
    pnu = str(pnu).strip()
    if len(pnu) != 19 or not pnu.isdigit():
        return None
    return {
        "pnu": pnu,
        "year": year,
        "price_per_m2": _parse_int(price_raw),
        "source": "official_land_price",
        "raw_data": raw,
    }


def compute_change_rate(current: int, previous: int | None) -> float | None:
    """Return YoY change as a percentage (e.g. ``5.32`` for +5.32 %).

    Returns ``None`` if there's no previous price (so the first-year rows
    aren't false-zeroed).
    """
    if not previous:
        return None
    return round((current - previous) / previous * 100, 4)


class LandPriceClient:
    """Async client for V-World 개별공시지가 API."""

    def __init__(
        self,
        api_key: str | None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._client = client
        self._owns_client = False

    async def __aenter__(self) -> LandPriceClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                headers={"User-Agent": USER_AGENT_DEFAULT},
            )
            self._owns_client = True
        return self

    async def __aexit__(self, *_exc: object) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()

    async def fetch_year(
        self,
        year: int,
        *,
        pnu_list: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if self._client is None:
            raise RuntimeError("LandPriceClient must be used as an async ctx mgr")
        rows: list[dict[str, Any]] = []
        targets: Iterable[str | None] = pnu_list or [None]
        for pnu in targets:
            params: dict[str, Any] = {
                "key": self._api_key or "",
                "stdrYear": str(year),
                "format": "json",
                "domain": "realestate-analyzer",
            }
            if pnu:
                params["pnu"] = pnu
            response = await http_get_with_retry(
                self._client, self._base_url, params=params
            )
            payload = response.json()
            items = payload.get("indvdLandPrices") or payload.get("items") or []
            for item in items if isinstance(items, list) else [items]:
                if isinstance(item, dict):
                    rows.append(item)
        return rows


async def fetch_previous_prices(
    session: AsyncSession,
    *,
    pnus: list[str],
    year: int,
) -> dict[str, int]:
    """Load last-year prices for the given PNUs to compute change rates."""
    if not pnus:
        return {}
    stmt = select(
        OfficialLandPrice.pnu, OfficialLandPrice.price_per_m2
    ).where(
        OfficialLandPrice.pnu.in_(pnus),
        OfficialLandPrice.year == year - 1,
    )
    result = await session.execute(stmt)
    return {row.pnu: row.price_per_m2 for row in result}


async def upsert_land_prices(
    session: AsyncSession,
    rows: Iterable[dict[str, Any]],
    *,
    dry_run: bool = False,
) -> int:
    rows_list = list(rows)
    accepted = 0
    if not rows_list:
        return 0

    pnus = [r["pnu"] for r in rows_list]
    year = rows_list[0]["year"]
    prev = (
        {} if dry_run else await fetch_previous_prices(session, pnus=pnus, year=year)
    )

    for row in rows_list:
        try:
            row_with_change = {
                **row,
                "change_rate": compute_change_rate(
                    row["price_per_m2"], prev.get(row["pnu"])
                ),
            }
            stmt = (
                pg_insert(OfficialLandPrice)
                .values(**row_with_change)
                .on_conflict_do_update(
                    constraint="uq_official_land_prices_pnu_year",
                    set_={
                        "price_per_m2": row_with_change["price_per_m2"],
                        "change_rate": row_with_change["change_rate"],
                        "raw_data": row_with_change["raw_data"],
                    },
                )
            )
            if not dry_run:
                await session.execute(stmt)
            accepted += 1
        except Exception as exc:  # noqa: BLE001
            log_row_error(pipeline=PIPELINE_NAME, row=row, error=str(exc))
    return accepted


async def _run(
    year: int,
    *,
    pnu_list: list[str] | None,
    dry_run: bool,
) -> dict[str, int]:
    check_kill_switch()
    settings = get_settings()
    async with LandPriceClient(settings.realty_price_api_key) as client:
        raw_rows = await client.fetch_year(year, pnu_list=pnu_list)
    normalized = [
        n for r in raw_rows
        if (n := normalize_row(r, year=year)) is not None
    ]

    if dry_run:
        LOGGER.info("land_price_dry_run", year=year, normalized=len(normalized))
        return {
            "fetched": len(raw_rows),
            "normalized": len(normalized),
            "upserted": 0,
        }

    engine = create_async_engine(settings.database_url, future=True)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as session, session.begin():
            upserted = await upsert_land_prices(session, normalized)
    finally:
        await engine.dispose()
    return {
        "fetched": len(raw_rows),
        "normalized": len(normalized),
        "upserted": upserted,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="개별공시지가 ETL")
    parser.add_argument("--year", required=True, type=int)
    parser.add_argument(
        "--pnu-list", help="Path to a newline-separated PNU file (optional)."
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    pnu_list = None
    if args.pnu_list:
        from pathlib import Path  # noqa: PLC0415

        pnu_list = [
            line.strip()
            for line in Path(args.pnu_list).read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        ]

    configure_logging()
    counts = asyncio.run(
        _run(args.year, pnu_list=pnu_list, dry_run=args.dry_run)
    )
    print(f"LandPrice ETL: {counts}")  # noqa: T201


if __name__ == "__main__":
    main()
