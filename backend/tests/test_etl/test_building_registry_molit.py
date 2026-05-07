"""Unit tests for the MOLIT 건축물대장 (data.go.kr) adapter."""

from __future__ import annotations

import httpx
import pytest
import respx

from src.etl import building_registry_molit as etl


# ─── PNU decomposition ─────────────────────────────────────────────────────


def test_pnu_to_params_decomposes_strict_19_digit_pnu() -> None:
    out = etl.pnu_to_params("1168010100108250021")
    assert out == {
        "sigunguCd": "11680",
        "bjdongCd": "10100",
        "platGbCd": "1",
        "bun": "0825",
        "ji": "0021",
    }


def test_pnu_to_params_strips_hyphens() -> None:
    """The PNU sometimes arrives in dashed form — accept it transparently."""
    out = etl.pnu_to_params("1168010100-1-0825-0021")
    assert out is not None
    assert out["sigunguCd"] == "11680"
    assert out["bun"] == "0825"


def test_pnu_to_params_rejects_malformed_input() -> None:
    assert etl.pnu_to_params("12345") is None
    assert etl.pnu_to_params("not-a-pnu") is None
    assert etl.pnu_to_params("11680101001082500219") is None  # 20 digits


# ─── normalize_row ──────────────────────────────────────────────────────────


def test_normalize_row_returns_none_on_empty_input() -> None:
    assert etl.normalize_row({}, pnu="0" * 19) is None


def test_normalize_row_maps_BldRgst_fields() -> None:
    raw = {
        "newPlatPlc": "서울특별시 강남구 역삼로 123",
        "platPlc": "서울특별시 강남구 역삼동 825-21",
        "platArea": "265.7",
        "archArea": "180.5",
        "totArea": "950.0",
        "grndFlrCnt": "5",
        "ugrndFlrCnt": "1",
        "mainPurpsCdNm": "근린생활시설",
        "strctCdNm": "철근콘크리트조",
        "useAprDay": "20180312",
        "bldNm": "역삼타워",
    }
    out = etl.normalize_row(raw, pnu="1168010100108250021")
    assert out is not None
    assert out["pnu"] == "1168010100108250021"
    assert out["address"] == "서울특별시 강남구 역삼로 123"
    assert out["parcel_area_m2"] == 265.7
    assert out["building_area_m2"] == 180.5
    assert out["total_floor_area_m2"] == 950.0
    assert out["floors_above"] == 5
    assert out["floors_below"] == 1
    assert out["use_type"] == "근린생활시설"
    assert out["structure"] == "철근콘크리트조"
    assert out["approval_date"] == "20180312"
    assert out["building_name"] == "역삼타워"
    assert out["source"] == "molit:bldrgst"


# ─── HTTP layer ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_one_decomposes_pnu_into_query_params() -> None:
    """Verifies the request carries sigunguCd / bjdongCd / platGbCd / bun / ji."""
    captured: dict = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={"response": {"body": {"items": {
            "item": [{"newPlatPlc": "addr", "platArea": "100"}]
        }}}})

    with respx.mock() as router:
        router.get(etl.DEFAULT_BASE_URL).mock(side_effect=_capture)
        async with etl.MolitBuildingRegistryClient(api_key="x") as client:
            row = await client.fetch_one("1168010100108250021")

    assert captured["params"]["sigunguCd"] == "11680"
    assert captured["params"]["bjdongCd"] == "10100"
    assert captured["params"]["platGbCd"] == "1"
    assert captured["params"]["bun"] == "0825"
    assert captured["params"]["ji"] == "0021"
    assert row is not None
    assert row["address"] == "addr"


@pytest.mark.asyncio
async def test_fetch_one_returns_none_on_invalid_pnu() -> None:
    async with etl.MolitBuildingRegistryClient(api_key="x") as client:
        assert await client.fetch_one("invalid") is None


@pytest.mark.asyncio
async def test_fetch_one_returns_none_on_empty_response() -> None:
    payload = {"response": {"body": {"items": ""}}}
    with respx.mock() as router:
        router.get(etl.DEFAULT_BASE_URL).mock(
            return_value=httpx.Response(200, json=payload)
        )
        async with etl.MolitBuildingRegistryClient(api_key="x") as client:
            assert await client.fetch_one("1168010100108250021") is None
