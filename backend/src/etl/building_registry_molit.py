"""국토교통부 건축HUB 건축물대장 (data.go.kr) 어댑터.

Alternative to V-World ``getGeneralBuildingAttr`` which currently fails
with ``URL_TYPE`` for our keys. The data.go.kr 건축HUB service
returns the same field set and uses the same MOLIT key we already have.

Apply at: https://www.data.go.kr → search "건축HUB 건축물대장"
  → "국토교통부_건축HUB_건축물대장정보 서비스" → 활용신청 (auto-approved).

Endpoint family ``BldRgstHubService`` exposes 8+ operations; we use
``getBrTitleInfo`` (표제부) for the base building record. The API
expects the parcel decomposed into ``sigunguCd / bjdongCd / platGbCd
/ bun / ji`` rather than a single PNU — :func:`pnu_to_params` does
the split for us.

Note on propagation: a freshly-approved data.go.kr service can return
HTTP 403 for 5–30 minutes while the auth gateway syncs. Retry later if
the first call after approval rejects.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import httpx

from src.core.logging import app_logger
from src.etl.common import (
    USER_AGENT_DEFAULT,
    check_kill_switch,
    http_get_with_retry,
    log_row_error,
)

LOGGER = app_logger
PIPELINE_NAME = "building_registry_molit"

DEFAULT_BASE_URL = (
    "https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"
)


def pnu_to_params(pnu: str) -> dict[str, str] | None:
    """Decompose a 19-digit PNU into ``BldRgstService_v2`` query params.

    PNU layout (string positions, 0-indexed)::

        시도(2) + 시군구(3) + 읍면동(3) + 리(2) + 토지구분(1) + 본번(4) + 부번(4)

    Returns ``None`` for malformed input so callers can skip cleanly.
    """
    cleaned = pnu.replace("-", "")
    if len(cleaned) != 19 or not cleaned.isdigit():
        return None
    return {
        "sigunguCd": cleaned[0:5],   # 시도(2) + 시군구(3)
        "bjdongCd":  cleaned[5:10],  # 읍면동(3) + 리(2)
        "platGbCd":  cleaned[10],    # 0=대지, 1=산, 2=블록
        "bun":       cleaned[11:15],
        "ji":        cleaned[15:19],
    }


def _safe_int(v: Any) -> int | None:
    if v in (None, ""):
        return None
    try:
        return int(str(v).replace(",", "").strip())
    except ValueError:
        return None


def _safe_float(v: Any) -> float | None:
    if v in (None, ""):
        return None
    try:
        return float(str(v).replace(",", "").strip())
    except ValueError:
        return None


def normalize_row(raw: dict[str, Any], *, pnu: str) -> dict[str, Any] | None:
    """Map one ``getBrTitleInfo`` row to the same shape we use for V-World.

    Field names are stable — they match V-World's ``getGeneralBuildingAttr``
    response, so downstream code (``buildings`` model + Scenario C feature
    extractor) doesn't care which source produced the row.
    """
    if not raw:
        return None
    return {
        "pnu": pnu,
        "address": raw.get("newPlatPlc") or raw.get("platPlc"),
        "parcel_area_m2": _safe_float(raw.get("platArea")),
        "building_area_m2": _safe_float(raw.get("archArea")),
        "total_floor_area_m2": _safe_float(raw.get("totArea")),
        "floors_above": _safe_int(raw.get("grndFlrCnt")),
        "floors_below": _safe_int(raw.get("ugrndFlrCnt")),
        "use_type": raw.get("mainPurpsCdNm"),
        "structure": raw.get("strctCdNm"),
        "approval_date": raw.get("useAprDay"),  # YYYYMMDD string
        "building_name": raw.get("bldNm"),
        "source": "molit:bldrgst",
        "raw_data": raw,
    }


class MolitBuildingRegistryClient:
    """data.go.kr 건축물대장 ``BldRgstService_v2`` async client."""

    def __init__(
        self,
        api_key: str | None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._client = client
        self._owns_client = False

    async def __aenter__(self) -> MolitBuildingRegistryClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                headers={"User-Agent": USER_AGENT_DEFAULT},
            )
            self._owns_client = True
        return self

    async def __aexit__(self, *_exc: object) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()

    async def fetch_one(self, pnu: str) -> dict[str, Any] | None:
        """Return the first 표제부 row for ``pnu`` or ``None`` if missing."""
        check_kill_switch()
        if self._client is None:
            raise RuntimeError(
                "MolitBuildingRegistryClient must be used as ctx mgr"
            )

        params = pnu_to_params(pnu)
        if params is None:
            log_row_error(
                pipeline=PIPELINE_NAME,
                row={"pnu": pnu},
                error="invalid PNU format",
            )
            return None

        try:
            response = await http_get_with_retry(
                self._client,
                self._base_url,
                params={
                    "serviceKey": self._api_key or "",
                    **params,
                    "_type": "json",
                    "pageNo": "1",
                    "numOfRows": "1",
                },
            )
        except Exception as exc:  # noqa: BLE001
            log_row_error(pipeline=PIPELINE_NAME, row={"pnu": pnu}, error=str(exc))
            return None

        payload = response.json()
        body = payload.get("response", {}).get("body", {})
        items = body.get("items") or {}
        if isinstance(items, dict):
            item = items.get("item")
            if isinstance(item, list):
                rows: Iterable[dict[str, Any]] = (r for r in item if isinstance(r, dict))
            elif isinstance(item, dict):
                rows = [item]
            else:
                return None
        elif isinstance(items, list):
            rows = (r for r in items if isinstance(r, dict))
        else:
            return None

        first = next(iter(rows), None)
        return normalize_row(first, pnu=pnu) if first else None
