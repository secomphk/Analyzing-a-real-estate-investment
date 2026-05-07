"""Halo-effect analyzer for Scenario C.

For one store, compute distance-banded average parcel price changes
between a pre-open window and successive post-open windows, and net out
the same-시군구 baseline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

_DEFAULT_BANDS_M = (500, 1_000, 2_000, 3_000)
_HORIZONS_DAYS = {"+1y": 365, "+3y": 365 * 3, "+5y": 365 * 5}


@dataclass(slots=True, frozen=True)
class DistanceBandImpact:
    """Halo-effect for one (band, horizon) cell."""

    band_m: int
    horizon: str
    pre_avg_price_per_m2: float | None
    post_avg_price_per_m2: float | None
    change_pct: float | None
    baseline_pct: float | None
    halo_pct: float | None
    sample_pre: int
    sample_post: int


@dataclass(slots=True)
class StoreImpactResult:
    """Top-level return for the API."""

    store_id: int
    open_date: date
    bands: list[DistanceBandImpact]
    model_version: str = "scenario_c_v1.0.0"
    confidence_score: float = 0.5
    notes: list[str] = field(default_factory=list)


class StoreImpactAnalyzer:
    """Compute halo effect bands and the same-시군구 baseline."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def analyze(
        self,
        store_id: int,
        *,
        bands_m: tuple[int, ...] = _DEFAULT_BANDS_M,
        pre_window_days: int = 365,
    ) -> StoreImpactResult | None:
        meta = await self._fetch_store(store_id)
        if meta is None or meta["open_date"] is None:
            return None

        bands: list[DistanceBandImpact] = []
        notes: list[str] = []
        for band_m in bands_m:
            for horizon, days in _HORIZONS_DAYS.items():
                pre_avg, n_pre = await self._mean_price(
                    lat=meta["lat"], lng=meta["lng"],
                    band_m=band_m,
                    start=meta["open_date"] - timedelta(days=pre_window_days),
                    end=meta["open_date"],
                )
                post_avg, n_post = await self._mean_price(
                    lat=meta["lat"], lng=meta["lng"],
                    band_m=band_m,
                    start=meta["open_date"],
                    end=meta["open_date"] + timedelta(days=days),
                )
                change_pct = _pct(post_avg, pre_avg)
                baseline_pct = await self._baseline_change(
                    region_code=meta["region_code"],
                    open_date=meta["open_date"],
                    horizon_days=days,
                    pre_window_days=pre_window_days,
                )
                halo = (
                    change_pct - baseline_pct
                    if change_pct is not None and baseline_pct is not None
                    else None
                )
                bands.append(
                    DistanceBandImpact(
                        band_m=band_m,
                        horizon=horizon,
                        pre_avg_price_per_m2=pre_avg,
                        post_avg_price_per_m2=post_avg,
                        change_pct=_round(change_pct),
                        baseline_pct=_round(baseline_pct),
                        halo_pct=_round(halo),
                        sample_pre=n_pre,
                        sample_post=n_post,
                    )
                )

        # Confidence saturates with sample size in the 500m band, +1y horizon.
        primary = next(
            (b for b in bands if b.band_m == 500 and b.horizon == "+1y"),
            None,
        )
        if primary is None or primary.sample_post == 0:
            notes.append("핵심 거리대(500m, +1y)에 거래 표본이 없습니다.")
        confidence = _confidence(bands)

        return StoreImpactResult(
            store_id=store_id,
            open_date=meta["open_date"],
            bands=bands,
            confidence_score=confidence,
            notes=notes,
        )

    # ─── DB helpers ─────────────────────────────────────────────────────

    async def _fetch_store(self, store_id: int) -> dict[str, Any] | None:
        sql = text(
            """
            SELECT
                s.id,
                s.region_code,
                s.opened_at AS open_date,
                ST_X(s.location) AS lng,
                ST_Y(s.location) AS lat
            FROM stores s
            WHERE s.id = :store_id
            """
        ).bindparams(bindparam("store_id", value=store_id))
        row = (await self._session.execute(sql)).mappings().first()
        return dict(row) if row else None

    async def _mean_price(
        self,
        *,
        lat: float,
        lng: float,
        band_m: int,
        start: date,
        end: date,
    ) -> tuple[float | None, int]:
        sql = text(
            """
            SELECT
                AVG(deal_amount_krw / NULLIF(area_m2, 0)) AS avg_price,
                COUNT(*)                                  AS n
            FROM land_transactions
            WHERE location IS NOT NULL
              AND area_m2 > 0
              AND ST_DWithin(
                  location::geography,
                  ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography,
                  :band_m
              )
              AND contract_date >= :start
              AND contract_date <  :end
            """
        ).bindparams(
            bindparam("lat", value=lat),
            bindparam("lng", value=lng),
            bindparam("band_m", value=band_m),
            bindparam("start", value=start),
            bindparam("end", value=end),
        )
        row = (await self._session.execute(sql)).first()
        if row is None or row.avg_price is None:
            return None, int(row.n if row else 0)
        return float(row.avg_price), int(row.n)

    async def _baseline_change(
        self,
        *,
        region_code: str,
        open_date: date,
        horizon_days: int,
        pre_window_days: int,
    ) -> float | None:
        sql = text(
            """
            SELECT
                AVG(CASE
                    WHEN contract_date < :open_date THEN deal_amount_krw / NULLIF(area_m2, 0)
                    ELSE NULL
                END) AS pre_avg,
                AVG(CASE
                    WHEN contract_date >= :open_date THEN deal_amount_krw / NULLIF(area_m2, 0)
                    ELSE NULL
                END) AS post_avg
            FROM land_transactions
            WHERE region_code = :region_code
              AND area_m2 > 0
              AND contract_date >= :pre_start
              AND contract_date <= :post_end
            """
        ).bindparams(
            bindparam("region_code", value=region_code),
            bindparam("open_date", value=open_date),
            bindparam("pre_start", value=open_date - timedelta(days=pre_window_days)),
            bindparam("post_end", value=open_date + timedelta(days=horizon_days)),
        )
        row = (await self._session.execute(sql)).first()
        if row is None or row.pre_avg is None or row.post_avg is None:
            return None
        if float(row.pre_avg) == 0:
            return None
        return float(row.post_avg - row.pre_avg) / float(row.pre_avg)


# ─── Helpers ───────────────────────────────────────────────────────────────


def _pct(post: float | None, pre: float | None) -> float | None:
    if pre is None or post is None or pre == 0:
        return None
    return float(post - pre) / float(pre)


def _round(v: float | None, *, ndigits: int = 4) -> float | None:
    return None if v is None else round(v, ndigits)


def _confidence(bands: list[DistanceBandImpact]) -> float:
    """Confidence saturates as the number of band/horizon cells with data grows."""
    populated = sum(
        1 for b in bands if b.sample_pre > 0 and b.sample_post > 0
    )
    base = 0.30
    cap = 0.85
    scale = min(populated / max(len(bands), 1), 1.0)
    return round(base + (cap - base) * scale, 3)
