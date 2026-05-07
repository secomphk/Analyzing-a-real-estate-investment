"""건축물대장 (세움터) ETL — Scenario C 보조.

세움터는 봇 자동화에 적대적이고, 약관도 일괄 조회를 제한합니다. 따라서 이
파이프라인은:

* 입력 PNU 목록을 파일에서 읽어 (CSV / .txt)
* 가능한 영역만 자동 조회 (V-World 건축물 API)
* 자동화 한계 시 수기 입력용 CSV 템플릿을 출력

CLI::

    python -m src.etl.building_registry --pnu-list pnus.txt
    python -m src.etl.building_registry --pnu-list pnus.txt --csv-out tmpl.csv
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import re
from collections.abc import Iterable
from pathlib import Path
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
from src.models import Building

LOGGER = app_logger
PIPELINE_NAME = "building_registry"

DEFAULT_BASE_URL = "https://api.vworld.kr/ned/data/getGeneralBuildingAttr"
PNU_PATTERN = re.compile(r"^\d{19}$")


def load_pnu_list(path: Path) -> list[str]:
    """Read newline-separated PNUs.

    Skips blank lines and ``#``-prefixed comments. Validates that each PNU
    is 19 digits — anything else is logged and dropped.
    """
    pnus: list[str] = []
    with path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            # Tolerate hyphen-formatted PNUs ("1234567890-1-0001-0000").
            cleaned = line.replace("-", "")
            if PNU_PATTERN.fullmatch(cleaned):
                pnus.append(cleaned)
            else:
                LOGGER.warning(
                    "building_registry_invalid_pnu", line=line, pipeline=PIPELINE_NAME
                )
    return pnus


def normalize_row(raw: dict[str, Any], *, pnu: str) -> dict[str, Any] | None:
    """Map upstream V-World JSON to ``buildings`` shape."""
    if not raw:
        return None
    return {
        "pnu": pnu,
        "address": raw.get("newPlatPlc") or raw.get("address"),
        "parcel_area_m2": _safe_float(raw.get("platArea") or raw.get("parcel_area_m2")),
        "building_area_m2": _safe_float(raw.get("archArea") or raw.get("building_area_m2")),
        "total_floor_area_m2": _safe_float(
            raw.get("totArea") or raw.get("total_floor_area_m2")
        ),
        "floors_above": _safe_int(raw.get("grndFlrCnt") or raw.get("floors_above")),
        "floors_below": _safe_int(raw.get("ugrndFlrCnt") or raw.get("floors_below")),
        "use_type": raw.get("mainPurpsCdNm") or raw.get("use_type"),
        "structure": raw.get("strctCdNm") or raw.get("structure"),
        "approval_date": raw.get("useAprDay") or raw.get("approval_date"),
        "source": "vworld:building",
        "raw_data": raw,
    }


def _safe_int(v: Any) -> int | None:
    if v in (None, ""):
        return None
    try:
        return int(str(v).replace(",", "").strip())
    except ValueError:
        return None


def _safe_float(v: Any) -> float | None:
    if v in (None, ""):
        return None
    try:
        return float(str(v).replace(",", "").strip())
    except ValueError:
        return None


class BuildingRegistryClient:
    """V-World 일반 건축물 attribute API."""

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

    async def __aenter__(self) -> BuildingRegistryClient:
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

    async def fetch_one(self, pnu: str) -> dict[str, Any] | None:
        if self._client is None:
            raise RuntimeError("BuildingRegistryClient must be used as ctx mgr")
        params = {
            "key": self._api_key or "",
            "pnu": pnu,
            "format": "json",
            "domain": "realestate-analyzer",
        }
        response = await http_get_with_retry(
            self._client, self._base_url, params=params
        )
        payload = response.json()
        items = (
            payload.get("buildings", {}).get("field")
            or payload.get("items")
            or []
        )
        if isinstance(items, list) and items:
            return items[0] if isinstance(items[0], dict) else None
        if isinstance(items, dict):
            return items
        return None


async def upsert_buildings(
    session: AsyncSession,
    rows: Iterable[dict[str, Any]],
    *,
    dry_run: bool = False,
) -> int:
    accepted = 0
    for row in rows:
        try:
            stmt = (
                pg_insert(Building)
                .values(**row)
                .on_conflict_do_update(
                    index_elements=[Building.pnu],
                    set_={
                        "address": row["address"],
                        "use_type": row["use_type"],
                        "approval_date": row["approval_date"],
                        "raw_data": row["raw_data"],
                    },
                )
            )
            if not dry_run:
                await session.execute(stmt)
            accepted += 1
        except Exception as exc:  # noqa: BLE001
            log_row_error(pipeline=PIPELINE_NAME, row=row, error=str(exc))
    return accepted


def write_manual_csv_template(pnus: list[str], path: Path) -> Path:
    """Emit a CSV that operators fill in by hand for parcels we can't auto-fetch."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow([
            "pnu", "address", "parcel_area_m2", "building_area_m2",
            "total_floor_area_m2", "floors_above", "floors_below",
            "use_type", "structure", "approval_date(YYYY-MM-DD)", "note",
        ])
        for pnu in pnus:
            writer.writerow([pnu, "", "", "", "", "", "", "", "", "", ""])
    return path


async def _run(
    pnu_list_path: Path,
    *,
    csv_out: Path | None,
    dry_run: bool,
) -> dict[str, int]:
    check_kill_switch()
    pnus = load_pnu_list(pnu_list_path)
    LOGGER.info("building_registry_loaded_pnus", count=len(pnus))

    settings = get_settings()
    fetched: list[dict[str, Any]] = []
    failures: list[str] = []
    async with BuildingRegistryClient(settings.realty_price_api_key) as client:
        for pnu in pnus:
            try:
                raw = await client.fetch_one(pnu)
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("building_registry_fetch_failed", pnu=pnu, error=str(exc))
                failures.append(pnu)
                continue
            if raw is None:
                failures.append(pnu)
                continue
            normalized = normalize_row(raw, pnu=pnu)
            if normalized is not None:
                fetched.append(normalized)

    if csv_out and failures:
        write_manual_csv_template(failures, csv_out)
        LOGGER.info("building_registry_template_written", path=str(csv_out),
                    count=len(failures))

    if dry_run:
        return {
            "input_pnus": len(pnus),
            "fetched": len(fetched),
            "manual_template_rows": len(failures),
            "upserted": 0,
        }

    engine = create_async_engine(settings.database_url, future=True)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as session, session.begin():
            upserted = await upsert_buildings(session, fetched)
    finally:
        await engine.dispose()
    return {
        "input_pnus": len(pnus),
        "fetched": len(fetched),
        "manual_template_rows": len(failures),
        "upserted": upserted,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="건축물대장 ETL")
    parser.add_argument("--pnu-list", required=True, help="Path to PNU list (txt).")
    parser.add_argument(
        "--csv-out",
        help="Where to write the manual-input CSV template for failures.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    configure_logging()
    counts = asyncio.run(
        _run(
            Path(args.pnu_list),
            csv_out=Path(args.csv_out) if args.csv_out else None,
            dry_run=args.dry_run,
        )
    )
    print(f"BuildingRegistry ETL: {counts}")  # noqa: T201


if __name__ == "__main__":
    main()
