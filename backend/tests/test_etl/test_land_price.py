"""Unit tests for the 개별공시지가 ETL."""

from __future__ import annotations

import httpx
import pytest
import respx

from src.etl import land_price as etl


def test_normalize_row_rejects_invalid_pnu() -> None:
    assert etl.normalize_row({"pnu": "12345", "price": 100}, year=2024) is None
    assert etl.normalize_row({"pnu": "abcd" * 4 + "abc", "price": 100}, year=2024) is None
    # Valid 19-digit PNU survives.
    valid = "0" * 19
    assert etl.normalize_row({"pnu": valid, "price": 100}, year=2024) is not None


def test_change_rate_first_year_is_none() -> None:
    assert etl.compute_change_rate(1_500_000, None) is None


def test_change_rate_typical_growth() -> None:
    rate = etl.compute_change_rate(1_575_000, 1_500_000)
    assert rate == 5.0


def test_change_rate_zero_previous_returns_none() -> None:
    assert etl.compute_change_rate(1_575_000, 0) is None


@pytest.mark.asyncio
async def test_fetch_year_iterates_pnu_list() -> None:
    pnus = ["1" * 19, "2" * 19]
    seen_params: list[dict[str, str]] = []

    def _capture(request: httpx.Request) -> httpx.Response:
        seen_params.append(dict(request.url.params))
        return httpx.Response(200, json={"indvdLandPrices": [
            {"pnu": request.url.params["pnu"], "indvdLandPrice": "1234567"}
        ]})

    with respx.mock() as router:
        router.get(etl.DEFAULT_BASE_URL).mock(side_effect=_capture)
        async with etl.LandPriceClient(api_key="x") as client:
            rows = await client.fetch_year(2024, pnu_list=pnus)

    assert len(rows) == 2
    assert {p["pnu"] for p in seen_params} == set(pnus)
    assert all(p["stdrYear"] == "2024" for p in seen_params)
