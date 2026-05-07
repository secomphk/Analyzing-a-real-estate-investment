"""Unit tests for the V-World 토지특성 client."""

from __future__ import annotations

import httpx
import pytest
import respx

from src.etl import land_characteristics as lc


def test_normalize_row_parses_numeric_fields() -> None:
    raw = {
        "stdrYear": "2024",
        "ldCpsgCode": "41280",
        "lndpclAr": "1,480.50",
        "lndcgrCodeNm": "대",
        "prposArea1Nm": "제2종일반주거지역",
        "prposArea2Nm": "",
        "ladUseSittnNm": "상업용",
        "tpgrphHgCodeNm": "평지",
        "tpgrphFrmCodeNm": "정방형",
        "roadSideCodeNm": "광대로한면",
    }
    out = lc.normalize_row(raw, pnu="4128010500100010001")
    assert out is not None
    assert out["pnu"] == "4128010500100010001"
    assert out["stdr_year"] == 2024
    assert out["land_area_m2"] == 1480.5
    assert out["land_category"] == "대"
    assert out["use_district_1"] == "제2종일반주거지역"
    assert out["road_side_class"] == "광대로한면"


def test_normalize_row_handles_empty_input() -> None:
    assert lc.normalize_row({}, pnu="0" * 19) is None


@pytest.mark.asyncio
async def test_fetch_one_unwraps_field_array() -> None:
    pnu = "4128010500100010001"
    payload = {
        "landCharacteristicss": {
            "field": [
                {
                    "stdrYear": "2024",
                    "ldCpsgCode": "41280",
                    "lndpclAr": "1480.5",
                    "lndcgrCodeNm": "대",
                    "prposArea1Nm": "제2종일반주거지역",
                    "ladUseSittnNm": "상업용",
                    "tpgrphHgCodeNm": "평지",
                    "tpgrphFrmCodeNm": "정방형",
                    "roadSideCodeNm": "광대로한면",
                }
            ]
        }
    }
    with respx.mock() as router:
        router.get(lc.DEFAULT_BASE_URL).mock(
            return_value=httpx.Response(200, json=payload)
        )
        async with lc.LandCharacteristicsClient(api_key="test") as client:
            row = await client.fetch_one(pnu, year=2024)

    assert row is not None
    assert row["land_area_m2"] == 1480.5
    assert row["use_district_1"] == "제2종일반주거지역"


@pytest.mark.asyncio
async def test_fetch_one_returns_none_on_empty_field() -> None:
    payload = {"landCharacteristicss": {"field": []}}
    with respx.mock() as router:
        router.get(lc.DEFAULT_BASE_URL).mock(
            return_value=httpx.Response(200, json=payload)
        )
        async with lc.LandCharacteristicsClient(api_key="test") as client:
            assert await client.fetch_one("0" * 19) is None
