"""Geocoding abstraction.

Originally we planned to use Kakao Local API. As of 2024 the Local API
requires a Business App registration (사업자 인증) which is overkill for
our MVP. We replaced it with a small adapter that supports two backends:

* :class:`NaverGeocoder` — Naver Open API. Free tier (25,000 req/day),
  no business cert needed for read-only place search. The values look
  like WGS84 × 10⁷ — divide by 10⁷ for standard lat/lng.
* :class:`VWorldGeocoder` — V-World 주소 → 좌표 변환 (Step 2).
  Already on the roadmap; useful when we have only an address string.

For one-off design-time work (seed data refinement), the MCP-backed
``KakaoMap-SearchPlaceByKeywordOpen`` and ``NaverSearch-search_local``
tools work directly inside the agent context — see
``scripts/enrich_seed_coords.py`` for an example.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential


@dataclass(slots=True, frozen=True)
class GeocodeResult:
    """One resolved place."""

    name: str
    address: str | None
    road_address: str | None
    latitude: float
    longitude: float
    raw: dict[str, Any]


class Geocoder(ABC):
    """Common interface every backend implements."""

    @abstractmethod
    async def search(self, query: str, *, limit: int = 5) -> list[GeocodeResult]:
        """Return ``limit`` best matches for the keyword query."""


class NaverGeocoder(Geocoder):
    """Naver Open API client (no business cert required).

    Apply at https://developers.naver.com → Local Search.
    """

    BASE_URL = "https://openapi.naver.com/v1/search/local.json"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._client = client

    async def __aenter__(self) -> NaverGeocoder:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10)
            self._owns_client = True
        else:
            self._owns_client = False
        return self

    async def __aexit__(self, *_exc: object) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
        retry=retry_if_exception_type(httpx.HTTPError),
        reraise=True,
    )
    async def search(self, query: str, *, limit: int = 5) -> list[GeocodeResult]:
        if self._client is None:
            raise RuntimeError("NaverGeocoder must be used as an async context manager")
        response = await self._client.get(
            self.BASE_URL,
            params={"query": query, "display": min(limit, 5)},
            headers={
                "X-Naver-Client-Id": self._client_id,
                "X-Naver-Client-Secret": self._client_secret,
            },
        )
        response.raise_for_status()
        return [self._row_to_result(item) for item in response.json().get("items", [])]

    @staticmethod
    def _row_to_result(item: dict[str, Any]) -> GeocodeResult:
        # Naver returns coords as int strings: WGS84 × 10⁷.
        lng = float(item["mapx"]) / 1e7
        lat = float(item["mapy"]) / 1e7
        # Strip <b> highlight tags from the title.
        name = item.get("title", "").replace("<b>", "").replace("</b>", "")
        return GeocodeResult(
            name=name,
            address=item.get("address") or None,
            road_address=item.get("roadAddress") or None,
            latitude=lat,
            longitude=lng,
            raw=item,
        )


class VWorldGeocoder(Geocoder):
    """V-World 주소 → 좌표 (Step 2 backend)."""

    BASE_URL = "https://api.vworld.kr/req/address"

    def __init__(self, api_key: str, *, client: httpx.AsyncClient | None = None) -> None:
        self._api_key = api_key
        self._client = client

    async def __aenter__(self) -> VWorldGeocoder:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10)
            self._owns_client = True
        else:
            self._owns_client = False
        return self

    async def __aexit__(self, *_exc: object) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
        retry=retry_if_exception_type(httpx.HTTPError),
        reraise=True,
    )
    async def search(self, query: str, *, limit: int = 1) -> list[GeocodeResult]:
        if self._client is None:
            raise RuntimeError("VWorldGeocoder must be used as an async context manager")
        # V-World expects a structured address; treat ``query`` as the address.
        response = await self._client.get(
            self.BASE_URL,
            params={
                "service": "address",
                "request": "getCoord",
                "version": "2.0",
                "crs": "epsg:4326",
                "address": query,
                "type": "road",  # try road address first
                "format": "json",
                "key": self._api_key,
            },
        )
        response.raise_for_status()
        body = response.json().get("response", {})
        if body.get("status") != "OK":
            return []
        result = body.get("result", {})
        point = result.get("point", {})
        return [
            GeocodeResult(
                name=result.get("crs", "vworld"),
                address=body.get("input", {}).get("address"),
                road_address=body.get("input", {}).get("address"),
                latitude=float(point.get("y", 0)),
                longitude=float(point.get("x", 0)),
                raw=body,
            )
        ][:limit]
