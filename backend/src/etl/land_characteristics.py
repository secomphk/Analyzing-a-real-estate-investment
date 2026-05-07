"""V-World 토지특성 (getLandCharacteristics) 어댑터.

While the V-World ``일반건축물`` service is awaiting console activation,
``토지특성`` is already available with the same key and covers most of
the parcel-level fields we need for Scenario C feature engineering:

- ``ldCpsgCode``        시군구 코드
- ``lndpclAr``           토지 면적 (m²)
- ``lndcgrCodeNm``       지목 (대지/도로/임야 등)
- ``prposArea1Nm`` / ``prposArea2Nm``    용도지역 1·2
- ``ladUseSittnNm``      토지이용상황
- ``tpgrphHgCodeNm`` / ``tpgrphFrmCodeNm`` 지형 고저·형상
- ``roadSideCodeNm``     도로접면 (광대로/중로/소로/맹지)

The class follows the same async-context-manager pattern as
:class:`LandPriceClient` and :class:`BuildingRegistryClient` so it
plugs into the existing feature pipeline naturally.
"""

from __future__ import annotations

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
PIPELINE_NAME = "land_characteristics"

DEFAULT_BASE_URL = "https://api.vworld.kr/ned/data/getLandCharacteristics"


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
    """Map upstream V-World JSON to a flat Python dict.

    Returns ``None`` if the row is empty / missing identifying fields.
    """
    if not raw:
        return None
    return {
        "pnu": pnu,
        "stdr_year": _safe_int(raw.get("stdrYear")),
        "region_code": raw.get("ldCpsgCode"),
        "land_area_m2": _safe_float(raw.get("lndpclAr")),
        "land_category": raw.get("lndcgrCodeNm"),         # 지목
        "use_district_1": raw.get("prposArea1Nm"),        # 용도지역 1
        "use_district_2": raw.get("prposArea2Nm"),        # 용도지역 2
        "land_use_situation": raw.get("ladUseSittnNm"),   # 이용상황
        "elevation_class": raw.get("tpgrphHgCodeNm"),     # 지형 고저
        "topology_class": raw.get("tpgrphFrmCodeNm"),     # 지형 형상
        "road_side_class": raw.get("roadSideCodeNm"),     # 도로접면
        "raw": raw,
    }


class LandCharacteristicsClient:
    """V-World 토지특성 attribute API."""

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

    async def __aenter__(self) -> LandCharacteristicsClient:
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

    async def fetch_one(
        self, pnu: str, *, year: int | None = None
    ) -> dict[str, Any] | None:
        """Return the latest characteristics row for ``pnu``.

        ``year`` defaults to the most recent year V-World has indexed
        (``stdrYear`` filter). Pass an explicit year for historical lookups.
        """
        check_kill_switch()
        if self._client is None:
            raise RuntimeError(
                "LandCharacteristicsClient must be used as ctx mgr"
            )
        params: dict[str, Any] = {
            "key": self._api_key or "",
            "format": "json",
            "domain": "localhost",
            "pnu": pnu,
            "numOfRows": "1",
        }
        if year is not None:
            params["stdrYear"] = str(year)

        try:
            response = await http_get_with_retry(
                self._client, self._base_url, params=params
            )
        except Exception as exc:  # noqa: BLE001 — log + continue
            log_row_error(
                pipeline=PIPELINE_NAME,
                row={"pnu": pnu, "year": year},
                error=str(exc),
            )
            return None

        payload = response.json()
        container = payload.get("landCharacteristicss", {})
        if not isinstance(container, dict):
            return None
        # V-World wraps the data in `landCharacteristicss.field` (note: 2 's's).
        items = container.get("field") or []
        if isinstance(items, list) and items:
            row = items[0]
            return normalize_row(row, pnu=pnu) if isinstance(row, dict) else None
        if isinstance(items, dict):
            return normalize_row(items, pnu=pnu)
        return None
