"""McDonald's Korea store catalogue scraper.

Same fetch + pure-parse split as :mod:`starbucks` so tests can mock the
HTTP layer in isolation.
"""

from __future__ import annotations

from typing import Any

from src.etl.store_scraper.base import BaseStoreScraper, StoreData

LIST_URL = "https://www.mcdonalds.co.kr/api/store/list"


class McDonaldsScraper(BaseStoreScraper):
    """Concrete scraper for 맥도날드 매장."""

    brand_name = "맥도날드"
    brand_slug = "mcdonalds"
    base_url = "https://www.mcdonalds.co.kr"

    async def fetch_all_stores(self) -> list[StoreData]:
        response = await self.get(LIST_URL)
        payload = response.json()
        return [s for s in self._parse(payload) if s is not None]

    def _parse(self, payload: dict[str, Any]) -> list[StoreData]:
        items = payload.get("stores") or payload.get("data") or []
        return [
            self._row_to_store(row)
            for row in items
            if isinstance(row, dict)
        ]

    def _row_to_store(self, row: dict[str, Any]) -> StoreData:
        name = str(row.get("name") or row.get("storeName") or "").strip()
        return StoreData(
            source_id=str(row.get("id") or row.get("storeId") or row.get("code")),
            name=name,
            address=str(row.get("address") or row.get("addr") or "").strip(),
            latitude=float(row.get("lat") or row.get("latitude") or 0.0),
            longitude=float(row.get("lng") or row.get("longitude") or 0.0),
            store_type=self.classify_dt(name, row),
            source_url=(
                f"{self.base_url}/kor/store/detail.do?id={row.get('id')}"
                if row.get("id")
                else None
            ),
            raw=row,
        )
