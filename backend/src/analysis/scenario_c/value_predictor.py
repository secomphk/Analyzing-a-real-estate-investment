"""Land-value forecaster (1y / 3y / 5y).

Phase 1 ships a deterministic exponential-trend extrapolation calibrated
on the per-PNU price series + a catalyst booster. This avoids a hard
dependency on Prophet (which pulls cmdstan) for the API smoke path while
preserving the interface Phase 2 will swap in.

Phase 2 will replace ``_fit_pnu_trend`` with ``Prophet`` (plus an XGBoost
regressor over engineered residuals).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import numpy as np
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(slots=True, frozen=True)
class LandValueForecast:
    """Predicted land-price growth for a parcel at three horizons."""

    pnu: str
    base_year: int
    base_price_per_m2: int
    forecast: dict[str, float]        # {"1y": pct, "3y": pct, "5y": pct}
    method: str
    model_version: str = "scenario_c_v1.0.0"
    confidence_score: float = 0.5
    extra: dict[str, Any] = field(default_factory=dict)


# ─── Predictor ─────────────────────────────────────────────────────────────


class LandValuePredictor:
    """Forecast cumulative price growth at three horizons."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        catalyst_lift: float = 0.04,
    ) -> None:
        self._session = session
        self._catalyst_lift = catalyst_lift

    async def forecast(
        self,
        pnu: str,
        *,
        catalysts: dict[str, float] | None = None,
    ) -> LandValueForecast:
        rows = await self._fetch_price_series(pnu)
        if not rows:
            return LandValueForecast(
                pnu=pnu,
                base_year=date.today().year,
                base_price_per_m2=0,
                forecast={"1y": 0.0, "3y": 0.0, "5y": 0.0},
                method="empty",
                confidence_score=0.0,
            )

        years = np.array([r["year"] for r in rows], dtype=np.float64)
        prices = np.array([r["price"] for r in rows], dtype=np.float64)
        base_year = int(years[-1])
        base_price = int(prices[-1])

        # Exponential trend: log(price) ~ a + b * year. Fall back to
        # (last - first) / years when only two points exist.
        log_prices = np.log(prices.clip(min=1.0))
        if len(years) >= 3:
            slope, _ = np.polyfit(years, log_prices, deg=1)
        elif len(years) == 2:
            slope = (log_prices[1] - log_prices[0]) / (years[1] - years[0])
        else:
            slope = 0.0
        annual_growth = float(np.expm1(slope))

        # Catalyst booster: each catalyst variable adds a fixed YoY lift,
        # capped at +10 %/year so the surface stays sane.
        catalyst_score = _catalyst_score(catalysts)
        boosted_annual = float(np.clip(annual_growth + catalyst_score * self._catalyst_lift,
                                       -0.20, 0.30))

        forecast = {
            f"{h}y": round(float((1 + boosted_annual) ** h - 1), 4)
            for h in (1, 3, 5)
        }

        return LandValueForecast(
            pnu=pnu,
            base_year=base_year,
            base_price_per_m2=base_price,
            forecast=forecast,
            method="loglinear+catalyst",
            confidence_score=round(min(0.40 + 0.10 * len(years), 0.85), 3),
            extra={
                "annual_growth": round(annual_growth, 4),
                "catalyst_score": round(catalyst_score, 4),
                "boosted_annual": round(boosted_annual, 4),
                "n_observations": len(years),
            },
        )

    async def _fetch_price_series(self, pnu: str) -> list[dict[str, Any]]:
        sql = text(
            """
            SELECT year, price_per_m2 AS price
            FROM official_land_prices
            WHERE pnu = :pnu
            ORDER BY year
            """
        ).bindparams(bindparam("pnu", value=pnu))
        return [dict(r) for r in (await self._session.execute(sql)).mappings().all()]


def _catalyst_score(catalysts: dict[str, float] | None) -> float:
    """Map raw catalyst features to a single bounded score in [-1, +1].

    Defaults are conservative: missing keys do not influence the forecast.
    """
    if not catalysts:
        return 0.0
    weights = {
        "nearby_road_expansion": 0.25,
        "nearby_new_town": 0.30,
        "subway_extension_planned": 0.25,
        "population_growth_3y_pct": 1.50,
        "transaction_count_growth_3y": 0.50,
    }
    score = 0.0
    for key, weight in weights.items():
        v = float(catalysts.get(key, 0.0))
        score += weight * v
    return float(np.clip(score, -1.0, 1.0))
