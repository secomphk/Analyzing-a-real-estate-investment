"""Starbucks store catalogue scraper.

The public site exposes a JSON endpoint on ``store.starbucks.co.kr`` for
the store-search modal. The exact request shape is brittle and has changed
several times; ``fetch_all_stores`` is therefore split into a fetch step
(easy to mock) and a parse step (pure transform).

For Stage 2 the URL constants live as module-level defaults so tests can
inject a stub server without touching production code.
"""

from __future__ import annotations

from typing import Any

from src.etl.store_scraper.base import BaseStoreScraper, StoreData

LIST_URL = "https://store.starbucks.co.kr/getStore/rest/getAllStore"


class StarbucksScraper(BaseStoreScraper):
    """Concrete scraper for 스타벅스 매장."""

    brand_name = "스타벅스"
    brand_slug = "starbucks"
    base_url = "https://store.starbucks.co.kr"

    async def fetch_all_stores(self) -> list[StoreData]:
        response = await self.get(LIST_URL)
        payload = response.json()
        return [s for s in self._parse(payload) if s is not None]

    # Pure transform — testable without HTTP.
    def _parse(self, payload: dict[str, Any]) -> list[StoreData]:
        items = payload.get("list") or payload.get("items") or []
        return [
            self._row_to_store(row)
            for row in items
            if isinstance(row, dict)
        ]

    def _row_to_store(self, row: dict[str, Any]) -> StoreData:
        name = str(row.get("s_name") or row.get("name") or "").strip()
        return StoreData(
            source_id=str(row.get("s_code") or row.get("id") or row.get("storeNo")),
            name=name,
            address=str(row.get("addr") or row.get("address") or "").strip(),
            latitude=float(row.get("lat") or row.get("latitude") or 0.0),
            longitude=float(row.get("lot") or row.get("longitude") or 0.0),
            store_type=self.classify_dt(name, row),
            source_url=f"{self.base_url}/store/store-detail.do?id={row.get('s_code')}",
            raw=row,
        )
