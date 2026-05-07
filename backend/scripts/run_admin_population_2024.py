"""One-shot driver: pull 2024 monthly population for 평택 + 김포.

Used to verify the ``_ensure_admin_areas`` fix in
``src.etl.admin_population`` — should produce non-zero upserts for both
시군구 across all 12 months of 2024.

Run from ``backend/`` with the local Postgres stack up::

    python -m scripts.run_admin_population_2024
"""

from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.core.config import get_settings
from src.core.logging import app_logger, configure_logging
from src.etl.admin_population import (
    AdminPopulationClient,
    normalize_row,
    upsert_population,
)

LOGGER = app_logger

# 평택시 4122xxxxxx, 김포시 4128xxxxxx — 6-digit (시도+시군구) prefixes
# accepted by admmCd. data.go.kr expects the 10-digit prefix; the trailing
# zeros restrict the search to that 시군구 sub-tree.
TARGETS = [
    ("4122000000", "평택시"),
    ("4128000000", "김포시"),
]
MONTHS = [f"2024-{m:02d}" for m in range(1, 13)]


async def main() -> None:
    configure_logging()
    settings = get_settings()
    engine = create_async_engine(settings.database_url, future=True)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    grand_total: dict[str, int] = {"fetched": 0, "normalized": 0, "upserted": 0}
    per_target: dict[str, dict[str, int]] = {}

    try:
        async with AdminPopulationClient(settings.admin_population_api_key) as client:
            for admm_cd, label in TARGETS:
                target_total = {"fetched": 0, "normalized": 0, "upserted": 0}
                for ym in MONTHS:
                    try:
                        raw_rows = await client.fetch_month(
                            ym, admm_cd=admm_cd, lv=3, page_size=100
                        )
                    except Exception as exc:  # noqa: BLE001
                        LOGGER.warning(
                            "admin_population_fetch_failed",
                            admm_cd=admm_cd, month=ym, error=str(exc),
                        )
                        continue
                    normalized: list[dict[str, Any]] = [
                        n for r in raw_rows
                        if (n := normalize_row(r, year_month=ym)) is not None
                    ]
                    if not normalized:
                        LOGGER.info(
                            "admin_population_empty",
                            admm_cd=admm_cd, month=ym, fetched=len(raw_rows),
                        )
                        continue
                    async with Session() as session, session.begin():
                        upserted = await upsert_population(session, normalized)
                    LOGGER.info(
                        "admin_population_month",
                        admm_cd=admm_cd, label=label, month=ym,
                        fetched=len(raw_rows),
                        normalized=len(normalized),
                        upserted=upserted,
                    )
                    target_total["fetched"] += len(raw_rows)
                    target_total["normalized"] += len(normalized)
                    target_total["upserted"] += upserted
                per_target[label] = target_total
                grand_total["fetched"] += target_total["fetched"]
                grand_total["normalized"] += target_total["normalized"]
                grand_total["upserted"] += target_total["upserted"]
    finally:
        await engine.dispose()

    print("\n=== AdminPopulation 2024 backfill ===")  # noqa: T201
    for label, t in per_target.items():
        print(  # noqa: T201
            f"  {label}: fetched={t['fetched']} "
            f"normalized={t['normalized']} upserted={t['upserted']}"
        )
    print(  # noqa: T201
        f"  TOTAL : fetched={grand_total['fetched']} "
        f"normalized={grand_total['normalized']} upserted={grand_total['upserted']}"
    )


if __name__ == "__main__":
    asyncio.run(main())
