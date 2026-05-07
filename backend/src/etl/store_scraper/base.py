"""Abstract scraper base for DT/DI store catalogs.

Defines the polite-scraping contract that every concrete scraper inherits:

* respect ``robots.txt`` (caller can disable in tests).
* sleep ``request_delay_seconds`` between requests.
* honor an operator kill switch (``ETL_KILL_SWITCH=1``).
* identify the bot in ``User-Agent`` with a contact email.

The concrete scrapers (``starbucks.py``, ``mcdonalds.py``) implement
``fetch_all_stores`` by combining the helpers here.
"""

from __future__ import annotations

import asyncio
import urllib.robotparser
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from urllib.parse import urlparse

import httpx

from src.core.logging import app_logger
from src.etl.common import USER_AGENT_DEFAULT, check_kill_switch, http_get_with_retry

LOGGER = app_logger
DEFAULT_REQUEST_DELAY_SECONDS = 1.0


@dataclass(slots=True)
class StoreData:
    """Common shape every scraper produces.

    The seed/ETL pipeline maps this onto :class:`src.models.Store` rows.
    Brand identity is on the scraper instance, not the dataclass, since
    one scraper produces rows for exactly one brand.
    """

    source_id: str
    name: str
    address: str
    latitude: float
    longitude: float
    store_type: str            # "DT" / "DI" / "standard"
    source_url: str | None = None
    opened_at: date | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class BaseStoreScraper(ABC):
    """Inheritable contract for store catalogue scrapers."""

    brand_name: str    # Display name, may contain Korean (e.g. "스타벅스").
    brand_slug: str    # ASCII identifier used in HTTP headers / log fields.
    base_url: str

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        request_delay_seconds: float = DEFAULT_REQUEST_DELAY_SECONDS,
        respect_robots: bool = True,
        contact_email: str = "hokeunpark.hp@gmail.com",
    ) -> None:
        self._client = client
        self._owns_client = False
        self._request_delay = request_delay_seconds
        self._respect_robots = respect_robots
        # User-Agent must be ASCII per RFC 7230; route Korean display names
        # through ``brand_slug`` instead.
        self._user_agent = (
            f"{USER_AGENT_DEFAULT} (scraper:{self.brand_slug}; contact:{contact_email})"
        )
        self._robots_parser: urllib.robotparser.RobotFileParser | None = None

    # ─── Lifecycle ──────────────────────────────────────────────────────
    async def __aenter__(self) -> BaseStoreScraper:
        check_kill_switch()
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                headers={"User-Agent": self._user_agent},
                follow_redirects=True,
            )
            self._owns_client = True
        if self._respect_robots:
            await self._load_robots()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()

    # ─── Required ───────────────────────────────────────────────────────
    @abstractmethod
    async def fetch_all_stores(self) -> list[StoreData]:
        """Concrete subclasses iterate the brand's listing."""

    # ─── Helpers exposed to subclasses ──────────────────────────────────
    async def get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Polite GET: kill-switch + robots.txt + delay."""
        check_kill_switch()
        if self._client is None:
            raise RuntimeError(
                f"{self.brand_name} scraper must be used as an async context manager"
            )
        if self._robots_parser and not self._robots_parser.can_fetch(self._user_agent, url):
            raise PermissionError(f"robots.txt disallows: {url}")

        try:
            return await http_get_with_retry(self._client, url, params=params)
        finally:
            await asyncio.sleep(self._request_delay)

    @staticmethod
    def classify_dt(name: str, raw: dict[str, Any] | None = None) -> str:
        """Heuristic: name contains ``'DT'`` or raw flag set ⇒ ``"DT"``."""
        haystack = (name or "").upper()
        flag = (raw or {}).get("dt_flag") or (raw or {}).get("is_dt")
        if "DT" in haystack or "DRIVE" in haystack or flag in (True, "Y", "y", 1, "1"):
            return "DT"
        return "standard"

    # ─── Internal ───────────────────────────────────────────────────────
    async def _load_robots(self) -> None:
        if self._client is None:
            return
        parsed = urlparse(self.base_url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        try:
            response = await self._client.get(robots_url, timeout=5.0)
            self._robots_parser = urllib.robotparser.RobotFileParser()
            self._robots_parser.parse(response.text.splitlines())
        except httpx.HTTPError:
            LOGGER.warning("robots_unreachable", url=robots_url, brand=self.brand_slug)
            self._robots_parser = None
