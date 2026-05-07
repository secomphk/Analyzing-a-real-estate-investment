"""Unit tests for store scrapers + the kill switch."""

from __future__ import annotations

import time

import httpx
import pytest
import respx

from src.etl.common import KILL_SWITCH_ENV, KillSwitchActivated, check_kill_switch
from src.etl.store_scraper.base import BaseStoreScraper
from src.etl.store_scraper.mcdonalds import LIST_URL as MD_LIST
from src.etl.store_scraper.mcdonalds import McDonaldsScraper
from src.etl.store_scraper.starbucks import LIST_URL as SB_LIST
from src.etl.store_scraper.starbucks import StarbucksScraper


# ─── classify_dt heuristic ──────────────────────────────────────────────────


def test_classify_dt_picks_up_dt_in_name() -> None:
    assert BaseStoreScraper.classify_dt("김포한강신도시DT점") == "DT"
    assert BaseStoreScraper.classify_dt("Drive Thru Suwon") == "DT"
    assert BaseStoreScraper.classify_dt("강남대로점") == "standard"


def test_classify_dt_respects_explicit_flag() -> None:
    assert BaseStoreScraper.classify_dt("일반점", {"is_dt": True}) == "DT"
    assert BaseStoreScraper.classify_dt("일반점", {"dt_flag": "Y"}) == "DT"


# ─── Kill switch ────────────────────────────────────────────────────────────


def test_kill_switch_raises_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(KILL_SWITCH_ENV, "1")
    with pytest.raises(KillSwitchActivated):
        check_kill_switch()


def test_kill_switch_silent_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(KILL_SWITCH_ENV, raising=False)
    check_kill_switch()  # should not raise


# ─── Starbucks parse ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_starbucks_fetch_filters_dt() -> None:
    payload = {
        "list": [
            {"s_code": "100", "s_name": "운양DT점", "addr": "경기 김포 운양",
             "lat": 37.65, "lot": 126.65},
            {"s_code": "200", "s_name": "강남역점", "addr": "서울 강남",
             "lat": 37.50, "lot": 127.03},
        ]
    }
    with respx.mock() as router:
        router.get(SB_LIST).mock(return_value=httpx.Response(200, json=payload))
        async with StarbucksScraper(
            request_delay_seconds=0.0, respect_robots=False
        ) as scraper:
            stores = await scraper.fetch_all_stores()

    types = {s.source_id: s.store_type for s in stores}
    assert types == {"100": "DT", "200": "standard"}


# ─── McDonald's parse ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mcdonalds_fetch_extracts_coordinates() -> None:
    payload = {
        "stores": [
            {"id": "MD-001", "name": "동삭DT", "address": "평택 동삭",
             "lat": 36.98, "lng": 127.08},
        ]
    }
    with respx.mock() as router:
        router.get(MD_LIST).mock(return_value=httpx.Response(200, json=payload))
        async with McDonaldsScraper(
            request_delay_seconds=0.0, respect_robots=False
        ) as scraper:
            stores = await scraper.fetch_all_stores()

    assert len(stores) == 1
    s = stores[0]
    assert s.store_type == "DT"
    assert s.latitude == pytest.approx(36.98)
    assert s.longitude == pytest.approx(127.08)


# ─── Polite request delay ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_scraper_sleeps_between_requests() -> None:
    """Two consecutive ``get`` calls must be at least ``request_delay`` apart."""
    delay = 0.25
    with respx.mock() as router:
        router.get(SB_LIST).mock(return_value=httpx.Response(200, json={"list": []}))
        async with StarbucksScraper(
            request_delay_seconds=delay, respect_robots=False
        ) as scraper:
            t0 = time.perf_counter()
            await scraper.get(SB_LIST)
            await scraper.get(SB_LIST)
            elapsed = time.perf_counter() - t0
    # Two GETs ⇒ two delays. Allow some scheduler jitter.
    assert elapsed >= delay * 1.6, f"expected >= {delay * 1.6}s, got {elapsed:.3f}s"
