"""행정안전부 주민등록 인구통계 ETL — Scenario B 인구 시계열.

Source: data.go.kr 데이터셋 ``행정안전부_행정동별(통반단위) 주민등록 인구
및 세대현황``.

* Endpoint: ``https://apis.data.go.kr/1741000/admmPpltnHhStus/selectAdmmPpltnHhStus``
* Format:   JSON (set ``type=json``).
* Returned fields: 시도명, 시군구명, 행정동명, 통, 반, 총인구수, 세대수,
  세대당 인구, 남자인구수, 여자인구수, 남녀비율.
* Daily quota: 10,000 calls.

Note: this dataset returns admin-area NAMES (not codes). We attach the
matching ``region_code`` from the local ``admin_areas`` table at upsert
time so downstream queries stay keyed by code as the schema expects.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Iterable
from datetime import date, timedelta
from typing import Any

import httpx
from sqlalchemy import bindparam, text
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
from src.models import PopulationStat

LOGGER = app_logger
PIPELINE_NAME = "admin_population"

DEFAULT_BASE_URL = (
    "https://apis.data.go.kr/1741000/admmPpltnHhStus/selectAdmmPpltnHhStus"
)


def _parse_int(value: Any) -> int:
    if value is None or value == "":
        return 0
    return int(str(value).replace(",", "").strip())


def _parse_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return None


_ONE_DAY = timedelta(days=1)


def _month_end(year_month: str) -> date:
    """``"2024-01"`` → ``date(2024, 1, 31)``."""
    parts = year_month.replace("/", "-").split("-")
    year, month = int(parts[0]), int(parts[1])
    if month == 12:
        return date(year + 1, 1, 1) - _ONE_DAY
    return date(year, month + 1, 1) - _ONE_DAY


def normalize_row(raw: dict[str, Any], *, year_month: str) -> dict[str, Any] | None:
    """Map one upstream row to a partial ``population_stats`` payload.

    The data.go.kr ``admmPpltnHhStus`` response carries the 10-digit
    행정기관코드 (``admmCd``) — that's our ``region_code`` directly, so no
    name-based lookup is needed for new-schema rows. The function still
    accepts the deprecated ``jumin.mois.go.kr`` shape (``admin_code`` +
    ``total_population``) so existing fixtures don't break.

    Returns ``None`` when the row lacks both an identifier and a total.
    """
    # Current data.go.kr schema (preferred).
    admm_cd = raw.get("admmCd")
    sido = raw.get("ctpvNm") or raw.get("sidoNm") or raw.get("sido_nm")
    sigungu = raw.get("sggNm") or raw.get("sigungu_nm")
    dong = (
        raw.get("dongNm")          # current admmPpltnHhStus
        or raw.get("admmDongNm")   # earlier 행안부 endpoints
        or raw.get("emdNm")
        or raw.get("admm_dong_nm")
    )
    total = (
        raw.get("totNmprCnt")
        or raw.get("totNmpr")
        or raw.get("total_population")
        or raw.get("total")
    )
    households = (
        raw.get("hhCnt") or raw.get("households") or raw.get("household_count")
    )
    male = (
        raw.get("maleNmprCnt")     # current
        or raw.get("manNmprCnt")    # earlier
        or raw.get("malePopulation")
        or raw.get("male")
    )
    female = (
        raw.get("femlNmprCnt")     # current
        or raw.get("wmanNmprCnt")   # earlier
        or raw.get("femalePopulation")
        or raw.get("female")
    )
    hh_avg = (
        raw.get("hhNmpr")          # 세대당 인구
        or raw.get("hh_avg_population")
    )
    male_femL_rate = raw.get("maleFemlRate") or raw.get("genderRatio")
    tong = raw.get("tong")
    ban = raw.get("ban")

    # Legacy code-based fallback.
    legacy_code = raw.get("admin_code") or raw.get("region_code") or raw.get("code")
    region_code = admm_cd or legacy_code

    if not (region_code or sido) or total is None:
        return None

    return {
        # If the API returned admmCd directly, use it; otherwise leave None
        # so upsert_population resolves names → code against admin_areas.
        "region_code": str(region_code) if region_code else None,
        "sido_name": sido,
        "sigungu_name": sigungu,
        "dong_name": dong,
        "tong": tong or None,
        "ban": ban or None,
        "observed_at": _month_end(year_month),
        "total_population": _parse_int(total),
        "male_population": _parse_int(male),
        "female_population": _parse_int(female),
        "household_count": _parse_int(households),
        "avg_age": _parse_float(raw.get("avg_age") or raw.get("avgAge")),
        # Bonus fields surfaced for downstream feature engineering.
        "avg_household_size": _parse_float(hh_avg),
        "male_female_ratio": _parse_float(male_femL_rate),
        "source": "admin_population",
        "raw_data": raw,
    }


class AdminPopulationClient:
    """Async client for the 행정안전부 monthly snapshot endpoint."""

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

    async def __aenter__(self) -> AdminPopulationClient:
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

    async def fetch_month(
        self,
        year_month: str,
        *,
        admm_cd: str = "",
        lv: int = 3,
        reg_se_cd: int = 1,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        """Fetch population rows for ``year_month``.

        Parameters mirror the data.go.kr ``selectAdmmPpltnHhStus`` spec:

        * ``year_month`` — ``"YYYY-MM"`` or ``"YYYYMM"``. Sent as both
          ``srchFrYm`` and ``srchToYm`` (single-month query); the upstream
          allows up to a 3-month window.
        * ``admm_cd`` — 10-digit 행정기관코드 prefix. Empty string returns
          national results filtered only by ``lv``.
        * ``lv`` — 결과 구분: 1=시도, 2=시군구, 3=읍면동(default), 4=통,
          5=시도단일, 6=시군구단일, 7=읍면동단일.
        * ``reg_se_cd`` — 등록구분: 1=전체(default), 2=거주자, 3=거주불명자, 4=재외국민.
        * ``page_size`` — server caps at 100.
        """
        if self._client is None:
            raise RuntimeError("AdminPopulationClient must be used as an async ctx mgr")
        ym = year_month.replace("-", "")

        rows: list[dict[str, Any]] = []
        page = 1
        while True:
            params: dict[str, Any] = {
                "serviceKey": self._api_key or "",
                "admmCd": admm_cd,
                "srchFrYm": ym,
                "srchToYm": ym,
                "lv": str(lv),
                "regSeCd": str(reg_se_cd),
                "type": "json",
                "pageNo": str(page),
                "numOfRows": str(min(page_size, 100)),
            }

            response = await http_get_with_retry(
                self._client, self._base_url, params=params,
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
    """Pull row list from the data.go.kr response envelope.

    ``selectAdmmPpltnHhStus`` returns::

        {"Response": {"head": {...}, "items": {"item": [...]}}}
                  ^ capital R

    Legacy / sibling endpoints use lowercase ``response`` or
    dataset-named wrappers — we handle each so test fixtures and old
    code paths keep working.
    """
    for envelope_key in ("Response", "response"):
        env = payload.get(envelope_key)
        if not isinstance(env, dict):
            continue
        # Path 1: items.item (current admmPpltnHhStus + many MOLIT services).
        items = env.get("items") if "items" in env else env.get("body", {}).get("items")
        if isinstance(items, dict):
            item = items.get("item")
            if isinstance(item, list):
                return [r for r in item if isinstance(r, dict)]
            if isinstance(item, dict):
                return [item]
        if isinstance(items, list):
            return [r for r in items if isinstance(r, dict)]

    # Some 행안부 endpoints wrap rows under the dataset name + ``row``.
    for v in payload.values():
        if isinstance(v, dict) and "row" in v and isinstance(v["row"], list):
            return [r for r in v["row"] if isinstance(r, dict)]

    # Legacy fallbacks.
    direct = payload.get("data") or payload.get("items") or []
    if isinstance(direct, list):
        return [r for r in direct if isinstance(r, dict)]
    return []


def _extract_total_count(payload: dict[str, Any]) -> int | None:
    """Read ``totalCount`` from any of the response envelope shapes."""
    for envelope_key in ("Response", "response"):
        env = payload.get(envelope_key)
        if not isinstance(env, dict):
            continue
        # admmPpltnHhStus exposes head.totalCount (no body wrapper).
        head = env.get("head", {})
        if isinstance(head, dict) and head.get("totalCount") is not None:
            try:
                return int(str(head["totalCount"]).strip())
            except ValueError:
                return None
        body = env.get("body", {})
        if isinstance(body, dict) and body.get("totalCount") is not None:
            try:
                return int(str(body["totalCount"]).strip())
            except ValueError:
                return None
    # Dataset-named envelope.
    for v in payload.values():
        if isinstance(v, dict) and "totalCnt" in v:
            try:
                return int(str(v["totalCnt"]).strip())
            except ValueError:
                return None
    return None


async def _resolve_region_codes(
    session: AsyncSession, rows: list[dict[str, Any]]
) -> dict[tuple[str, str, str], str]:
    """Look up (sido, sigungu, dong) → ``admin_areas.code`` for the given rows.

    One DB hit total — we collect every unique name triple, then issue a
    single query against ``admin_areas``. Missing rows are simply absent
    from the returned dict (caller skips them).
    """
    triples = {
        (r["sido_name"] or "", r["sigungu_name"] or "", r["dong_name"] or "")
        for r in rows
        if r.get("sido_name") and r.get("dong_name")
    }
    if not triples:
        return {}
    # Match on the eupmyeondong-level name. The seed/ETL loads admin areas
    # with their plain ``name`` column — a join up the parent chain happens
    # inside Postgres for accuracy.
    sql = text(
        """
        WITH dongs AS (
            SELECT code, name, parent_code
            FROM admin_areas
            WHERE level = 'eupmyeondong'
        ),
        sigungus AS (
            SELECT code, name, parent_code FROM admin_areas WHERE level = 'sigungu'
        ),
        sidos AS (
            SELECT code, name FROM admin_areas WHERE level = 'sido'
        )
        SELECT
            sd.name AS sido,
            sg.name AS sigungu,
            d.name  AS dong,
            d.code  AS code
        FROM dongs d
        JOIN sigungus sg ON sg.code = d.parent_code
        JOIN sidos sd    ON sd.code = sg.parent_code
        WHERE d.name = ANY(:dong_names)
        """
    ).bindparams(bindparam("dong_names", value=[t[2] for t in triples]))
    result = await session.execute(sql)
    by_triple: dict[tuple[str, str, str], str] = {}
    for r in result:
        by_triple[(r.sido, r.sigungu, r.dong)] = r.code
    return by_triple


async def _ensure_admin_areas(
    session: AsyncSession, rows: list[dict[str, Any]]
) -> None:
    """Make sure every ``region_code`` referenced by ``rows`` exists in
    ``admin_areas`` so the FK on ``population_stats.region_code`` doesn't
    reject inserts.

    The data.go.kr ``admmCd`` is a stable 행정기관코드 that drills down to
    통/반 level — far more granular than the dongs we shipped in seed.
    For each new code we insert a minimal row tagged
    ``level='eupmyeondong'`` with the dong name (or full sido/sigungu/dong
    concatenation when present) and ``parent_code=NULL``. The row is
    enough to satisfy the FK; richer hierarchy can be backfilled later.
    """
    seen_codes: set[str] = set()
    payload = []
    for r in rows:
        code = r.get("region_code")
        if not code or code in seen_codes:
            continue
        seen_codes.add(code)
        # Build a friendly display name. data.go.kr returns blank tong/ban
        # at lv=3, so dongNm alone is usually enough.
        parts = [
            r.get("sido_name"),
            r.get("sigungu_name"),
            r.get("dong_name"),
        ]
        if r.get("tong"):
            parts.append(f"{r['tong']}통")
        if r.get("ban"):
            parts.append(f"{r['ban']}반")
        name = " ".join(p for p in parts if p) or code
        payload.append({"code": code, "name": name})

    if not payload:
        return

    stmt = text(
        """
        INSERT INTO admin_areas (code, name, level)
        SELECT * FROM unnest(
            CAST(:codes AS varchar[]),
            CAST(:names AS varchar[]),
            CAST(:levels AS admin_level[])
        )
        ON CONFLICT (code) DO NOTHING
        """
    ).bindparams(
        bindparam("codes", value=[p["code"] for p in payload]),
        bindparam("names", value=[p["name"] for p in payload]),
        bindparam("levels", value=["eupmyeondong"] * len(payload)),
    )
    await session.execute(stmt)


async def upsert_population(
    session: AsyncSession,
    rows: Iterable[dict[str, Any]],
    *,
    dry_run: bool = False,
) -> int:
    """UPSERT population rows.

    For data.go.kr rows that carry ``region_code`` (admmCd) directly we
    auto-create matching ``admin_areas`` entries first so the FK
    constraint always succeeds. For legacy name-only rows we fall back
    to :func:`_resolve_region_codes` against existing seed data.
    """
    rows_list = list(rows)
    if not rows_list:
        return 0

    # Auto-create admin_areas rows for any region_codes we don't have yet.
    if not dry_run:
        await _ensure_admin_areas(session, rows_list)

    # One round-trip to map (sido, sigungu, dong) → region_code, but only
    # for rows that don't already carry a code. Skipped entirely for dry
    # runs to keep the function offline-callable.
    code_lookup: dict[tuple[str, str, str], str] = {}
    if not dry_run:
        unresolved = [r for r in rows_list if not r.get("region_code")]
        if unresolved:
            code_lookup = await _resolve_region_codes(session, unresolved)

    accepted = 0
    for row in rows_list:
        try:
            region_code = row.get("region_code") or code_lookup.get(
                (
                    row.get("sido_name") or "",
                    row.get("sigungu_name") or "",
                    row.get("dong_name") or "",
                )
            )
            if not region_code:
                # No mapping — log and skip rather than poison the table.
                log_row_error(
                    pipeline=PIPELINE_NAME,
                    row=row,
                    error=(
                        f"Could not resolve region_code for "
                        f"{row.get('sido_name')!r} / {row.get('sigungu_name')!r} "
                        f"/ {row.get('dong_name')!r}"
                    ),
                )
                continue

            db_row = {
                "region_code": region_code,
                "observed_at": row["observed_at"],
                "total_population": row["total_population"],
                "male_population": row["male_population"],
                "female_population": row["female_population"],
                "household_count": row["household_count"],
                "avg_age": row["avg_age"],
                "source": row["source"],
                "raw_data": row["raw_data"],
            }

            stmt = (
                pg_insert(PopulationStat)
                .values(**db_row)
                .on_conflict_do_update(
                    constraint="uq_population_stats_region_observed_at",
                    set_={
                        "total_population": db_row["total_population"],
                        "male_population": db_row["male_population"],
                        "female_population": db_row["female_population"],
                        "household_count": db_row["household_count"],
                        "avg_age": db_row["avg_age"],
                        "raw_data": db_row["raw_data"],
                    },
                )
            )
            if not dry_run:
                await session.execute(stmt)
            accepted += 1
        except Exception as exc:  # noqa: BLE001
            log_row_error(pipeline=PIPELINE_NAME, row=row, error=str(exc))
    return accepted


async def _run(month: str, *, dry_run: bool) -> dict[str, int]:
    check_kill_switch()
    settings = get_settings()
    async with AdminPopulationClient(settings.admin_population_api_key) as client:
        raw_rows = await client.fetch_month(month)
    normalized = [
        n for r in raw_rows
        if (n := normalize_row(r, year_month=month)) is not None
    ]
    if dry_run:
        LOGGER.info("admin_population_dry_run", month=month,
                    fetched=len(raw_rows), normalized=len(normalized))
        return {"fetched": len(raw_rows), "normalized": len(normalized), "upserted": 0}

    engine = create_async_engine(settings.database_url, future=True)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as session, session.begin():
            upserted = await upsert_population(session, normalized)
    finally:
        await engine.dispose()
    return {
        "fetched": len(raw_rows),
        "normalized": len(normalized),
        "upserted": upserted,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="행정안전부 인구 ETL")
    parser.add_argument("--month", required=True, help="YYYY-MM")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    configure_logging()
    counts = asyncio.run(_run(args.month, dry_run=args.dry_run))
    print(f"AdminPopulation ETL: {counts}")  # noqa: T201


if __name__ == "__main__":
    main()
