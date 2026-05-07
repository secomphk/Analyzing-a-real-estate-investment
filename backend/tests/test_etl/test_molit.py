"""Unit tests for the MOLIT real-estate ETL.

Mocks the upstream API with respx — no network, no DB. The DB-touching
upsert is exercised against an in-memory FakeSession that captures the
ON-CONFLICT idempotency contract.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from src.etl import molit_real_estate as etl


def _two_page_response(page: int) -> dict[str, Any]:
    items = [
        {
            "일련번호": f"{page * 10 + i}",
            "년": "2024", "월": "1", "일": "15",
            "법정동": "운양동",
            "거래금액": f"{200_000 + i * 1_000:,}",
            "거래면적": "330.5",
            "용도지역": "제2종일반주거지역",
        }
        for i in range(2)
    ]
    return {
        "response": {
            "body": {
                "items": {"item": items},
                "totalCount": 4,
                "pageNo": page,
                "numOfRows": 2,
            }
        }
    }


def _one_item_response() -> dict[str, Any]:
    """API returns a single dict (not a list) when totalCount == 1."""
    return {
        "response": {
            "body": {
                "items": {
                    "item": {
                        "일련번호": "999",
                        "년": "2024", "월": "1", "일": "1",
                        "법정동": "장기동",
                        "거래금액": "150,000",
                        "거래면적": "210",
                        "용도지역": "준주거지역",
                    }
                },
                "totalCount": 1,
            }
        }
    }


# ─── normalize_row + make_source_id ─────────────────────────────────────────


def test_make_source_id_is_deterministic() -> None:
    a = etl.make_source_id(sigungu="41280", year_month="2024-01", serial="42")
    b = etl.make_source_id(sigungu="41280", year_month="2024-01", serial="42")
    assert a == b
    different = etl.make_source_id(sigungu="41280", year_month="2024-02", serial="42")
    assert a != different


def test_normalize_row_converts_korean_amount_to_won() -> None:
    raw = {
        "일련번호": "7", "년": "2024", "월": "01", "일": "15",
        "법정동": "운양동", "거래금액": "1,200,000", "거래면적": "350.5",
    }
    out = etl.normalize_row(raw, sigungu="41280", year_month="2024-01")
    # 1,200,000 (만원) × 10000 = 12,000,000,000 KRW
    assert out["deal_amount_krw"] == 12_000_000_000
    assert out["area_m2"] == 350.5
    assert out["transaction_type"] == "land"
    assert out["contract_date"] == "2024-01-15"
    assert out["region_code"] == "41280"


def test_normalize_row_handles_new_apis_data_go_kr_schema() -> None:
    """The 2024 data.go.kr gateway uses camelCase keys + omits 일련번호."""
    raw = {
        "dealYear": "2024", "dealMonth": "3", "dealDay": "15",
        "umdNm": "고덕면 당현리", "jibun": "2**",
        "dealAmount": "30,000",  # 3억원 = 만원 단위
        "dealArea": 331.0,
        "landUse": "농림지역",
        "sggCd": 41220,
        "dealingGbn": "중개거래",
    }
    out = etl.normalize_row(raw, sigungu="41220", year_month="2024-03")
    assert out["contract_date"] == "2024-03-15"
    assert out["deal_amount_krw"] == 300_000_000
    assert out["area_m2"] == 331.0
    assert out["use_district"] == "농림지역"
    assert out["address"] == "고덕면 당현리 2**"
    assert out["region_code"] == "41220"
    # No 일련번호 → derived from natural keys; should still be deterministic.
    assert out["source_id"]
    again = etl.normalize_row(raw, sigungu="41220", year_month="2024-03")
    assert again["source_id"] == out["source_id"]


# ─── HTTP fetch (respx) ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_month_paginates_until_total_reached() -> None:
    with respx.mock(assert_all_called=True) as router:
        page1 = router.get(etl.DEFAULT_BASE_URL, params={"pageNo": 1}).mock(
            return_value=httpx.Response(200, json=_two_page_response(1))
        )
        page2 = router.get(etl.DEFAULT_BASE_URL, params={"pageNo": 2}).mock(
            return_value=httpx.Response(200, json=_two_page_response(2))
        )

        async with etl.MolitClient(api_key="dummy") as client:
            rows = await client.fetch_month("41280", "2024-01", page_size=2)

        assert page1.called and page2.called
        assert len(rows) == 4


@pytest.mark.asyncio
async def test_fetch_month_handles_single_dict_item() -> None:
    with respx.mock() as router:
        router.get(etl.DEFAULT_BASE_URL).mock(
            return_value=httpx.Response(200, json=_one_item_response())
        )
        async with etl.MolitClient(api_key="dummy") as client:
            rows = await client.fetch_month("41280", "2024-01")
        assert len(rows) == 1
        assert rows[0]["법정동"] == "장기동"


@pytest.mark.asyncio
async def test_fetch_month_retries_on_5xx() -> None:
    with respx.mock() as router:
        attempts = router.get(etl.DEFAULT_BASE_URL).mock(
            side_effect=[
                httpx.Response(503),
                httpx.Response(503),
                httpx.Response(200, json=_one_item_response()),
            ]
        )
        async with etl.MolitClient(api_key="dummy") as client:
            rows = await client.fetch_month("41280", "2024-01")
        assert attempts.call_count == 3
        assert len(rows) == 1


# ─── Upsert (FakeSession) ───────────────────────────────────────────────────


class _FakeSession:
    """Minimal session that captures executed SQL statements without a DB."""

    def __init__(self) -> None:
        self.executed: list[Any] = []

    async def execute(self, stmt: Any) -> None:
        self.executed.append(stmt)


@pytest.mark.asyncio
async def test_upsert_runs_one_statement_per_row() -> None:
    session = _FakeSession()
    rows = [
        etl.normalize_row(
            {"일련번호": str(i), "년": "2024", "월": "1", "일": "1",
             "법정동": "운양동", "거래금액": "100,000", "거래면적": "300"},
            sigungu="41280", year_month="2024-01",
        )
        for i in range(3)
    ]
    accepted = await etl.upsert_transactions(session, rows)  # type: ignore[arg-type]
    assert accepted == 3
    assert len(session.executed) == 3


@pytest.mark.asyncio
async def test_upsert_dry_run_writes_nothing() -> None:
    session = _FakeSession()
    rows = [
        etl.normalize_row(
            {"일련번호": "1", "년": "2024", "월": "1", "일": "1",
             "법정동": "운양동", "거래금액": "100,000", "거래면적": "300"},
            sigungu="41280", year_month="2024-01",
        )
    ]
    accepted = await etl.upsert_transactions(session, rows, dry_run=True)  # type: ignore[arg-type]
    assert accepted == 1
    assert session.executed == []
