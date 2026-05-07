"""Unit tests for the 건축물대장 (V-World) ETL."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from src.etl import building_registry as etl


def test_load_pnu_list_skips_blank_and_comment_lines(tmp_path: Path) -> None:
    p = tmp_path / "pnus.txt"
    p.write_text(
        "\n".join([
            "# valid 19-digit PNU",
            "1111111111111111111",
            "",
            "  # comment with leading space",
            "2222222222222222222",
            "not-a-pnu",            # rejected
            "1234567890-1-0001-0000",  # hyphenated form, accepted
        ]),
        encoding="utf-8",
    )
    pnus = etl.load_pnu_list(p)
    assert pnus == [
        "1111111111111111111",
        "2222222222222222222",
        "1234567890100010000",
    ]


def test_normalize_row_maps_vworld_fields() -> None:
    raw = {
        "newPlatPlc": "경기 김포시 운양동 1234-5",
        "platArea": "1,480.50",
        "archArea": "320.00",
        "totArea": "448.00",
        "grndFlrCnt": "2",
        "ugrndFlrCnt": "0",
        "mainPurpsCdNm": "근린생활시설",
        "strctCdNm": "철골조",
        "useAprDay": "2018-11-30",
    }
    pnu = "1234567890123456789"
    out = etl.normalize_row(raw, pnu=pnu)
    assert out is not None
    assert out["pnu"] == pnu
    assert out["parcel_area_m2"] == 1480.5
    assert out["floors_above"] == 2
    assert out["use_type"] == "근린생활시설"
    assert out["approval_date"] == "2018-11-30"


def test_normalize_row_returns_none_on_empty_input() -> None:
    assert etl.normalize_row({}, pnu="0" * 19) is None


@pytest.mark.asyncio
async def test_fetch_one_unwraps_single_field_array() -> None:
    pnu = "1" * 19
    payload = {
        "buildings": {
            "field": [
                {"newPlatPlc": "Address", "platArea": "100"},
            ]
        }
    }
    with respx.mock() as router:
        router.get(etl.DEFAULT_BASE_URL).mock(
            return_value=httpx.Response(200, json=payload)
        )
        async with etl.BuildingRegistryClient(api_key="x") as client:
            row = await client.fetch_one(pnu)
    assert row is not None
    assert row["newPlatPlc"] == "Address"


def test_write_manual_csv_template_has_headers(tmp_path: Path) -> None:
    out = etl.write_manual_csv_template(["1" * 19, "2" * 19], tmp_path / "tmpl.csv")
    text = out.read_text(encoding="utf-8-sig")
    lines = text.strip().splitlines()
    assert lines[0].startswith("pnu,")
    assert "1111111111111111111" in lines[1]
    assert len(lines) == 3  # header + 2 rows
