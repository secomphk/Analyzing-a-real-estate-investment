"""국토교통부 실거래가 — Scenario A·B·C 공통.

Three building blocks:

1. ``MolitClient`` — async HTTP fetch with pagination + tenacity retries.
2. ``normalize_row`` — pure transform from upstream JSON into DB-shaped dicts.
3. ``upsert_transactions`` — idempotent bulk UPSERT keyed on ``source_id``.

CLI::

    python -m src.etl.molit_real_estate --sigungu 41280 --month 2024-01

Stage 2 ships a working skeleton; the upstream URL/format mirrors the
public API but specific field names should be tightened against the live
service before a production run.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
from collections.abc import Iterable
from typing import Any

import httpx
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
from src.models import LandTransaction

LOGGER = app_logger
PIPELINE_NAME = "molit_real_estate"

# Default endpoint — MOLIT migrated to the unified data.go.kr gateway in
# 2024. The legacy ``openapi.molit.go.kr`` host is being phased out.
DEFAULT_BASE_URL = (
    "https://apis.data.go.kr/1613000/RTMSDataSvcLandTrade"
    "/getRTMSDataSvcLandTrade"
)
PAGE_SIZE = 100


def _to_int(value: Any) -> int:
    """Parse '1,234,500' or '12345.0' into an int, swallowing junk."""
    if value is None or value == "":
        return 0
    if isinstance(value, int):
        return value
    cleaned = str(value).replace(",", "").strip()
    return int(float(cleaned)) if cleaned else 0


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    cleaned = str(value).replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def make_source_id(*, sigungu: str, year_month: str, serial: str | int) -> str:
    """Stable hash of the row key — used for UNIQUE-on-conflict UPSERTs."""
    raw = f"molit:{sigungu}:{year_month}:{serial}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:32]


def normalize_row(raw: dict[str, Any], *, sigungu: str, year_month: str) -> dict[str, Any]:
    """Convert one upstream row into a DB-ready dict.

    Field-name lookups try both the legacy Korean keys (returned by the
    deprecated ``openapi.molit.go.kr`` endpoint) and the camelCase keys
    used by the current ``apis.data.go.kr`` gateway. The new gateway
    omits a stable serial number, so when none is present we derive a
    deterministic ``source_id`` from the natural keys (sggCd + jibun +
    deal date + amount + area), which makes UPSERTs idempotent.
    """
    deal_year = raw.get("년") or raw.get("dealYear") or year_month.split("-")[0]
    deal_month = raw.get("월") or raw.get("dealMonth") or year_month.split("-")[1]
    deal_day = raw.get("일") or raw.get("dealDay") or "1"
    contract_date = (
        f"{int(deal_year):04d}-{int(deal_month):02d}-{int(deal_day):02d}"
    )

    # Address: 법정동 (legacy) → umdNm (new). Combine with jibun for completeness.
    dong = raw.get("법정동") or raw.get("umdNm") or raw.get("dong") or raw.get("address")
    jibun = raw.get("지번") or raw.get("jibun")
    address = (
        f"{dong} {jibun}".strip() if dong and jibun else (dong or jibun)
    )

    deal_amount_man = _to_int(raw.get("거래금액") or raw.get("dealAmount"))
    deal_area = _to_float(raw.get("거래면적") or raw.get("dealArea"))
    use_district = raw.get("용도지역") or raw.get("landUse") or raw.get("useArea")
    region_code = (
        str(raw.get("sggCd") or raw.get("법정동시군구코드") or "").strip() or sigungu
    )

    serial = raw.get("일련번호") or raw.get("serialNo") or raw.get("rnum")
    if serial:
        source_id = make_source_id(
            sigungu=sigungu, year_month=year_month, serial=serial,
        )
    else:
        # Natural key — stable across retries since these fields don't change
        # for an already-recorded transaction.
        natural = "|".join([
            region_code, contract_date, str(jibun or ""),
            str(deal_amount_man), str(deal_area or "0"),
        ])
        source_id = make_source_id(
            sigungu=sigungu, year_month=year_month, serial=natural,
        )

    return {
        "source_id": source_id,
        "source": "molit",
        "region_code": region_code,
        "pnu": (raw.get("pnu") or raw.get("PNU")) or None,
        "address": address,
        "transaction_type": "land",
        "contract_date": contract_date,
        "deal_amount_krw": (deal_amount_man * 10_000) if deal_amount_man
        else _to_int(raw.get("거래금액원")),
        "area_m2": deal_area,
        "use_district": use_district,
        "raw_data": raw,
    }


# ─── HTTP layer ─────────────────────────────────────────────────────────────


class MolitClient:
    """Thin async client around the MOLIT real-estate endpoint."""

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

    async def __aenter__(self) -> MolitClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                headers={"User-Agent": USER_AGENT_DEFAULT},
            )
            self._owns_client = True
        else:
            self._owns_client = False
        return self

    async def __aexit__(self, *_exc: object) -> None:
        if self._client is not None and getattr(self, "_owns_client", False):
            await self._client.aclose()

    async def fetch_month(
        self,
        sigungu: str,
        year_month: str,
        *,
        page_size: int = PAGE_SIZE,
    ) -> list[dict[str, Any]]:
        """Fetch every transaction for ``(sigungu, YYYY-MM)``, paginated.

        ``year_month`` accepts ``"YYYY-MM"`` or ``"YYYYMM"``.
        """
        if self._client is None:
            raise RuntimeError("MolitClient must be used as an async context manager")

        ym = year_month.replace("-", "")
        rows: list[dict[str, Any]] = []
        page = 1
        while True:
            params = {
                "serviceKey": self._api_key or "",
                "LAWD_CD": sigungu,
                "DEAL_YMD": ym,
                "pageNo": page,
                "numOfRows": page_size,
                "_type": "json",
            }
            response = await http_get_with_retry(
                self._client, self._base_url, params=params
            )
            payload = response.json()
            page_rows = _extract_items(payload)
            rows.extend(page_rows)
            total = _extract_total_count(payload)
            if total is None or len(rows) >= total or not page_rows:
                break
            page += 1
        return rows


def _extract_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Pull the ``items`` array out of MOLIT's nested response shape.

    Defensive — the API sometimes returns a single dict instead of a list
    when there is exactly one row.
    """
    body = payload.get("response", {}).get("body", {}) or payload.get("body", {})
    items = body.get("items") or {}
    if not items:
        return []
    item = items.get("item") if isinstance(items, dict) else items
    if isinstance(item, list):
        return [r for r in item if isinstance(r, dict)]
    if isinstance(item, dict):
        return [item]
    return []


def _extract_total_count(payload: dict[str, Any]) -> int | None:
    body = payload.get("response", {}).get("body", {}) or payload.get("body", {})
    raw = body.get("totalCount")
    return _to_int(raw) if raw is not None else None


# ─── DB layer ──────────────────────────────────────────────────────────────


async def upsert_transactions(
    session: AsyncSession,
    rows: Iterable[dict[str, Any]],
    *,
    dry_run: bool = False,
) -> int:
    """UPSERT rows into ``land_transactions`` keyed on ``source_id``.

    Returns the number of rows that survived normalization. Invalid rows
    are skipped and logged via :func:`log_row_error`.
    """
    accepted = 0
    for row in rows:
        try:
            stmt = (
                pg_insert(LandTransaction)
                .values(**row)
                .on_conflict_do_update(
                    constraint="uq_land_transactions_source_id",
                    set_={
                        "deal_amount_krw": row["deal_amount_krw"],
                        "area_m2": row["area_m2"],
                        "use_district": row["use_district"],
                        "raw_data": row["raw_data"],
                    },
                )
            )
            if not dry_run:
                await session.execute(stmt)
            accepted += 1
        except Exception as exc:  # noqa: BLE001 — we want to log + continue
            log_row_error(pipeline=PIPELINE_NAME, row=row, error=str(exc))
    return accepted


# ─── CLI ───────────────────────────────────────────────────────────────────


async def _run(sigungu: str, month: str, *, dry_run: bool) -> dict[str, int]:
    check_kill_switch()
    settings = get_settings()
    async with MolitClient(settings.molit_api_key) as client:
        raw_rows = await client.fetch_month(sigungu, month)

    normalized = [normalize_row(r, sigungu=sigungu, year_month=month) for r in raw_rows]

    if dry_run:
        LOGGER.info(
            "molit_dry_run", sigungu=sigungu, month=month,
            fetched=len(raw_rows), normalized=len(normalized),
        )
        return {"fetched": len(raw_rows), "normalized": len(normalized), "upserted": 0}

    engine = create_async_engine(settings.database_url, future=True)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as session, session.begin():
            upserted = await upsert_transactions(session, normalized)
    finally:
        await engine.dispose()

    LOGGER.info(
        "molit_complete", sigungu=sigungu, month=month,
        fetched=len(raw_rows), upserted=upserted,
    )
    return {
        "fetched": len(raw_rows),
        "normalized": len(normalized),
        "upserted": upserted,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="MOLIT 실거래가 ETL.")
    parser.add_argument("--sigungu", required=True, help="시군구 코드 (5 chars).")
    parser.add_argument("--month", required=True, help="YYYY-MM or YYYYMM.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    configure_logging()
    counts = asyncio.run(_run(args.sigungu, args.month, dry_run=args.dry_run))
    print(f"MOLIT ETL: {counts}")  # noqa: T201


if __name__ == "__main__":
    main()
