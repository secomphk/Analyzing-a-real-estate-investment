"""Unit tests for the 행정안전부 인구 ETL.

Two source schemas are exercised:

* the legacy ``jumin.mois.go.kr`` shape (``admin_code`` + ``total_population``),
  kept as a backward-compat path so old fixtures don't break;
* the current ``apis.data.go.kr/1741000/admmPpltnHhStus`` shape, which uses
  Korean-named camelCase fields (``ctpvNm`` / ``dongNm`` / ``totNmprCnt``)
  and an envelope keyed under capital ``Response`` with a head that holds
  ``totalCount``.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import httpx
import pytest
import respx

from src.etl import admin_population as etl


# ─── normalize_row ──────────────────────────────────────────────────────────


def test_normalize_row_returns_none_on_empty_payload() -> None:
    assert etl.normalize_row({}, year_month="2024-01") is None
    assert etl.normalize_row({"ctpvNm": "경기도"}, year_month="2024-01") is None


def test_normalize_row_legacy_admin_code_path() -> None:
    raw = {
        "admin_code": "4128010100",
        "total_population": "32,415",
        "male": "16,210",
        "female": "16,205",
        "households": "12,330",
    }
    out = etl.normalize_row(raw, year_month="2024-01")
    assert out is not None
    assert out["region_code"] == "4128010100"
    assert out["total_population"] == 32_415
    assert out["male_population"] == 16_210
    assert out["household_count"] == 12_330


def test_normalize_row_admmPpltnHhStus_schema() -> None:
    """Real response shape from /selectAdmmPpltnHhStus."""
    raw = {
        "admmCd": "4128151000",
        "statsYm": "202403",
        "ctpvNm": "경기도",
        "sggNm": "고양시 덕양구",
        "dongNm": "주교동",
        "tong": "",
        "ban": "",
        "totNmprCnt": "10911",
        "maleNmprCnt": "5679",
        "femlNmprCnt": "5232",
        "hhCnt": "5458",
        "hhNmpr": "2.00",
        "maleFemlRate": "1.09",
    }
    out = etl.normalize_row(raw, year_month="2024-03")
    assert out is not None
    # admmCd was returned directly — no name resolution needed.
    assert out["region_code"] == "4128151000"
    assert out["sido_name"] == "경기도"
    assert out["sigungu_name"] == "고양시 덕양구"
    assert out["dong_name"] == "주교동"
    assert out["total_population"] == 10_911
    assert out["male_population"] == 5_679
    assert out["female_population"] == 5_232
    assert out["household_count"] == 5_458
    assert out["avg_household_size"] == 2.0
    assert out["male_female_ratio"] == 1.09


def test_month_end_handles_year_boundaries() -> None:
    assert etl._month_end("2024-01") == date(2024, 1, 31)
    assert etl._month_end("2024-02") == date(2024, 2, 29)
    assert etl._month_end("2024-12") == date(2024, 12, 31)


# ─── HTTP layer (respx) ─────────────────────────────────────────────────────


def _build_payload(items: list[dict[str, Any]], total: int, page: int = 1) -> dict[str, Any]:
    """Mirror the real upstream envelope: capital-R Response with items.item."""
    return {
        "Response": {
            "head": {
                "pageNo": str(page),
                "totalCount": str(total),
                "numOfRows": "100",
                "resultCode": "0",
                "resultMsg": "NORMAL_SERVICE",
            },
            "items": {"item": items} if items else "",
        }
    }


@pytest.mark.asyncio
async def test_fetch_month_sends_required_params() -> None:
    """The endpoint requires admmCd, srchFrYm, srchToYm, lv, regSeCd."""
    captured: dict[str, Any] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json=_build_payload([
            {"admmCd": "4128010500", "ctpvNm": "경기도", "sggNm": "김포시",
             "dongNm": "운양동", "totNmprCnt": "10000", "hhCnt": "4000",
             "maleNmprCnt": "5100", "femlNmprCnt": "4900",
             "hhNmpr": "2.5", "maleFemlRate": "1.04",
             "tong": "", "ban": ""}
        ], total=1))

    with respx.mock() as router:
        router.get(etl.DEFAULT_BASE_URL).mock(side_effect=_capture)
        async with etl.AdminPopulationClient(api_key="x") as client:
            rows = await client.fetch_month("2024-03", admm_cd="4128010500", lv=3)

    p = captured["params"]
    assert p["srchFrYm"] == "202403"
    assert p["srchToYm"] == "202403"
    assert p["admmCd"] == "4128010500"
    assert p["lv"] == "3"
    assert p["regSeCd"] == "1"
    assert p["type"] == "json"
    assert len(rows) == 1
    assert rows[0]["dongNm"] == "운양동"


@pytest.mark.asyncio
async def test_fetch_month_paginates_until_total_reached() -> None:
    """Pagination walks until len(rows) >= totalCount or rows are empty."""
    page_calls = {"n": 0}

    def _serve(request: httpx.Request) -> httpx.Response:
        page_calls["n"] += 1
        page = int(request.url.params.get("pageNo", "1"))
        # 5 rows total, page_size=2 → 3 pages (2,2,1).
        slices = [
            [{"admmCd": f"410000000{i}", "totNmprCnt": "100",
              "ctpvNm": "S", "sggNm": "G", "dongNm": f"d{i}"} for i in (1, 2)],
            [{"admmCd": f"410000000{i}", "totNmprCnt": "100",
              "ctpvNm": "S", "sggNm": "G", "dongNm": f"d{i}"} for i in (3, 4)],
            [{"admmCd": "4100000005", "totNmprCnt": "100",
              "ctpvNm": "S", "sggNm": "G", "dongNm": "d5"}],
        ]
        items = slices[page - 1] if page <= len(slices) else []
        return httpx.Response(200, json=_build_payload(items, total=5, page=page))

    with respx.mock() as router:
        router.get(etl.DEFAULT_BASE_URL).mock(side_effect=_serve)
        async with etl.AdminPopulationClient(api_key="x") as client:
            rows = await client.fetch_month("2024-03", page_size=2)

    assert page_calls["n"] == 3
    assert len(rows) == 5
