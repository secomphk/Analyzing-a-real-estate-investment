"""Unit tests for the geocoder adapters.

Naver returns coordinates as integer strings × 10⁷; the adapter must
divide them back into proper WGS84 floats and strip the ``<b>`` highlight
tags from titles. V-World returns standard floats already.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from src.etl.geocoder import NaverGeocoder, VWorldGeocoder


# ─── NaverGeocoder ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_naver_normalises_coords_and_strips_b_tags() -> None:
    payload = {
        "items": [
            {
                "title": "<b>스타벅스</b> 평택비전<b>DT</b>점",
                "address": "경기도 평택시 비전동 17-1",
                "roadAddress": "경기도 평택시 비전4로 180",
                "mapx": "1271046308",
                "mapy": "370112538",
            }
        ]
    }
    with respx.mock() as router:
        router.get(NaverGeocoder.BASE_URL).mock(
            return_value=httpx.Response(200, json=payload)
        )
        async with NaverGeocoder("id", "secret") as g:
            results = await g.search("평택 비전동 스타벅스 DT")

    assert len(results) == 1
    r = results[0]
    assert r.name == "스타벅스 평택비전DT점"
    assert r.road_address == "경기도 평택시 비전4로 180"
    assert r.latitude == pytest.approx(37.0112538, rel=1e-6)
    assert r.longitude == pytest.approx(127.1046308, rel=1e-6)


@pytest.mark.asyncio
async def test_naver_empty_results() -> None:
    with respx.mock() as router:
        router.get(NaverGeocoder.BASE_URL).mock(
            return_value=httpx.Response(200, json={"items": []})
        )
        async with NaverGeocoder("id", "secret") as g:
            assert await g.search("nonexistent") == []


@pytest.mark.asyncio
async def test_naver_retries_on_5xx() -> None:
    """Tenacity retries the call up to 3 times on httpx.HTTPError."""
    with respx.mock() as router:
        attempts = router.get(NaverGeocoder.BASE_URL).mock(
            side_effect=[
                httpx.Response(503),
                httpx.Response(503),
                httpx.Response(
                    200, json={"items": [{
                        "title": "ok", "address": "addr",
                        "roadAddress": "addr",
                        "mapx": "1270000000", "mapy": "370000000",
                    }]},
                ),
            ]
        )
        async with NaverGeocoder("id", "secret") as g:
            results = await g.search("query")
        assert attempts.call_count == 3
        assert len(results) == 1


# ─── VWorldGeocoder ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_vworld_returns_wgs84() -> None:
    payload = {
        "response": {
            "status": "OK",
            "input": {"address": "경기 김포시 운양동"},
            "result": {"point": {"x": "126.6534", "y": "37.6517"}},
        }
    }
    with respx.mock() as router:
        router.get(VWorldGeocoder.BASE_URL).mock(
            return_value=httpx.Response(200, json=payload)
        )
        async with VWorldGeocoder("APIKEY") as g:
            results = await g.search("경기 김포시 운양동")

    assert len(results) == 1
    assert results[0].latitude == pytest.approx(37.6517)
    assert results[0].longitude == pytest.approx(126.6534)


@pytest.mark.asyncio
async def test_vworld_returns_empty_when_status_not_ok() -> None:
    with respx.mock() as router:
        router.get(VWorldGeocoder.BASE_URL).mock(
            return_value=httpx.Response(200, json={"response": {"status": "NOT_FOUND"}})
        )
        async with VWorldGeocoder("APIKEY") as g:
            assert await g.search("주소없음") == []
