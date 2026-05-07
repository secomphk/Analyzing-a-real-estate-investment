"""Scenario B — 3-variable analyzer.

Pulls a road's expansion-stage timeline + monthly traffic + abutting-area
population, joins them on (year, month), and emits:

* ``TimePoint``s — one row per month with normalized values.
* ``CorrelationMatrix`` — pairwise Pearson.
* ``LeadLagAnalysis`` — for the (population, traffic) pair.
* ``Insight`` list — natural-language conclusions for the API surface.

Performance budget: < 2s for 7 years × 1 road on a warm DB.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.analysis.common.normalizer import minmax_scale
from src.analysis.scenario_b.correlation import (
    CorrelationMatrix,
    pearson_matrix,
)
from src.analysis.scenario_b.lead_lag import (
    LeadLagAnalysis,
    LeadLagClassifier,
)


@dataclass(slots=True, frozen=True)
class TimePoint:
    """One aligned monthly observation."""

    year_month: str            # "YYYY-MM"
    population: float | None
    aadt: float | None
    road_progress: float       # 0.0 → 1.0 (planned → completed)


@dataclass(slots=True, frozen=True)
class Insight:
    """One natural-language insight + supporting numbers."""

    title: str
    detail: str
    score: float


@dataclass(slots=True)
class ThreeVariableResult:
    """Top-level output for the API."""

    road_id: int
    time_points: list[TimePoint]
    correlations: CorrelationMatrix
    lead_lag: LeadLagAnalysis | None
    insights: list[Insight] = field(default_factory=list)
    model_version: str = "scenario_b_v1.0.0"
    confidence_score: float = 0.0
    top_factors: list[dict[str, Any]] = field(default_factory=list)


# ─── Stage progress helper ─────────────────────────────────────────────────


_PROGRESS_BY_STAGE = {
    "planned": 0.10,
    "design": 0.30,
    "under_construction": 0.60,
    "completed": 1.00,
}


def _progress_for_month(stages: list[tuple[date, str]], month_first: date) -> float:
    """Latest stage progress as of ``month_first``.

    ``stages`` is sorted ascending by ``occurred_at``.
    """
    latest = 0.0
    for occurred_at, kind in stages:
        if occurred_at <= month_first:
            latest = _PROGRESS_BY_STAGE.get(kind, latest)
    return latest


# ─── Analyzer ──────────────────────────────────────────────────────────────


class ThreeVariableAnalyzer:
    """Top-level Scenario B engine.

    Pulls everything it needs from the DB through the injected
    :class:`AsyncSession` and runs entirely in memory afterwards.
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        lead_lag: LeadLagClassifier | None = None,
    ) -> None:
        self._session = session
        self._lead_lag = lead_lag or LeadLagClassifier()

    async def analyze(
        self,
        *,
        road_id: int,
        start: date | None = None,
        end: date | None = None,
    ) -> ThreeVariableResult:
        traffic = await self._fetch_traffic(road_id, start, end)
        if not traffic:
            return ThreeVariableResult(
                road_id=road_id,
                time_points=[],
                correlations=CorrelationMatrix(variables=[], matrix=[]),
                lead_lag=None,
                confidence_score=0.0,
                insights=[
                    Insight(
                        title="데이터 부족",
                        detail=(
                            "선택된 도로에 대한 통행량 시계열이 없습니다. "
                            "ETL을 먼저 실행한 후 다시 시도하세요."
                        ),
                        score=0.0,
                    )
                ],
            )

        # Population is the average across abutting admin codes.
        population = await self._fetch_population_for_road(road_id, start, end)
        stages = await self._fetch_stages(road_id)

        # Align on month_first.
        merged = self._align(traffic, population, stages)
        time_points = [
            TimePoint(
                year_month=mp["year_month"],
                population=mp["population"],
                aadt=mp["aadt"],
                road_progress=mp["road_progress"],
            )
            for mp in merged
        ]

        # Series with NaN replaced by linear interpolation for stat work.
        pop_series = _interpolate([m["population"] for m in merged])
        aadt_series = _interpolate([m["aadt"] for m in merged])
        prog_series = [m["road_progress"] for m in merged]

        # Min-max normalise so insights compare apples-to-apples.
        norm = {
            "road_progress": minmax_scale(prog_series).tolist(),
            "population": minmax_scale(pop_series).tolist(),
            "aadt": minmax_scale(aadt_series).tolist(),
        }
        corr = pearson_matrix(norm)
        lead_lag = self._lead_lag.analyze(
            a="population", b="aadt",
            series_a=norm["population"], series_b=norm["aadt"],
        )
        insights = _build_insights(corr, lead_lag, time_points)
        confidence = _confidence(time_points)
        top_factors = _top_factors(corr, lead_lag)

        return ThreeVariableResult(
            road_id=road_id,
            time_points=time_points,
            correlations=corr,
            lead_lag=lead_lag,
            insights=insights,
            confidence_score=confidence,
            top_factors=top_factors,
        )

    # ─── DB helpers ─────────────────────────────────────────────────────

    async def _fetch_traffic(
        self,
        road_id: int,
        start: date | None,
        end: date | None,
    ) -> list[dict[str, Any]]:
        sql = text(
            """
            SELECT observed_at, aadt
            FROM traffic_volumes
            WHERE road_id = :road_id
              AND (CAST(:start AS date) IS NULL OR observed_at >= :start)
              AND (CAST(:end   AS date) IS NULL OR observed_at <= :end)
            ORDER BY observed_at
            """
        ).bindparams(
            bindparam("road_id", value=road_id),
            bindparam("start", value=start),
            bindparam("end", value=end),
        )
        result = await self._session.execute(sql)
        return [{"observed_at": r.observed_at, "aadt": int(r.aadt)} for r in result]

    async def _fetch_population_for_road(
        self,
        road_id: int,
        start: date | None,
        end: date | None,
    ) -> list[dict[str, Any]]:
        sql = text(
            """
            SELECT
                ps.observed_at                      AS observed_at,
                AVG(ps.total_population)::int       AS total_population
            FROM population_stats ps
            -- region_code on road_segments is the 5-char 시군구 prefix
            -- (e.g. '41220'); on population_stats it's the 10-digit
            -- 행정기관코드 down to 통/반 level. Aggregate every dong row
            -- whose code starts with the road's 시군구.
            JOIN road_segments rs ON ps.region_code LIKE rs.region_code || '%'
            WHERE rs.id = :road_id
              AND (CAST(:start AS date) IS NULL OR ps.observed_at >= :start)
              AND (CAST(:end   AS date) IS NULL OR ps.observed_at <= :end)
            GROUP BY ps.observed_at
            ORDER BY ps.observed_at
            """
        ).bindparams(
            bindparam("road_id", value=road_id),
            bindparam("start", value=start),
            bindparam("end", value=end),
        )
        result = await self._session.execute(sql)
        return [
            {"observed_at": r.observed_at, "total_population": int(r.total_population)}
            for r in result
        ]

    async def _fetch_stages(self, road_id: int) -> list[tuple[date, str]]:
        sql = text(
            """
            SELECT occurred_at, stage
            FROM road_expansion_stages
            WHERE road_id = :road_id
            ORDER BY occurred_at
            """
        ).bindparams(bindparam("road_id", value=road_id))
        result = await self._session.execute(sql)
        return [(r.occurred_at, str(r.stage)) for r in result]

    # ─── In-memory join ─────────────────────────────────────────────────

    def _align(
        self,
        traffic: list[dict[str, Any]],
        population: list[dict[str, Any]],
        stages: list[tuple[date, str]],
    ) -> list[dict[str, Any]]:
        pop_by_month: dict[str, int] = {}
        for r in population:
            month_key = r["observed_at"].strftime("%Y-%m")
            pop_by_month[month_key] = r["total_population"]

        out: list[dict[str, Any]] = []
        for r in traffic:
            month_key = r["observed_at"].strftime("%Y-%m")
            month_first = r["observed_at"].replace(day=1)
            out.append(
                {
                    "year_month": month_key,
                    "population": float(pop_by_month.get(month_key, float("nan"))),
                    "aadt": float(r["aadt"]),
                    "road_progress": _progress_for_month(stages, month_first),
                }
            )
        return out


# ─── Pure helpers ──────────────────────────────────────────────────────────


def _interpolate(values: Sequence[float]) -> list[float]:
    """Fill NaN by linear interpolation so correlation stays well-defined."""
    import math  # noqa: PLC0415

    arr = list(values)
    n = len(arr)
    if n == 0:
        return arr
    # Forward-fill leading NaN with first valid value.
    valid_idx = [i for i, v in enumerate(arr) if not math.isnan(v)]
    if not valid_idx:
        return [0.0] * n
    first = valid_idx[0]
    for i in range(first):
        arr[i] = arr[first]
    last = valid_idx[-1]
    for i in range(last + 1, n):
        arr[i] = arr[last]
    # Linear interpolation between valid points.
    for k in range(len(valid_idx) - 1):
        lo, hi = valid_idx[k], valid_idx[k + 1]
        if hi == lo + 1:
            continue
        for j in range(lo + 1, hi):
            t = (j - lo) / (hi - lo)
            arr[j] = arr[lo] + t * (arr[hi] - arr[lo])
    return arr


def _build_insights(
    corr: CorrelationMatrix,
    lead_lag: LeadLagAnalysis,
    points: list[TimePoint],
) -> list[Insight]:
    insights: list[Insight] = []

    if "road_progress" in corr.variables and "aadt" in corr.variables:
        c = corr.get("road_progress", "aadt")
        if abs(c) >= 0.5:
            polarity = "양의" if c > 0 else "음의"
            insights.append(
                Insight(
                    title="도로 진행률 ↔ 통행량 연동",
                    detail=(
                        f"도로 단계 진행과 통행량 사이에 {polarity} 강한 상관"
                        f" (r={c:+.2f})이 관찰됩니다."
                    ),
                    score=round(abs(c), 4),
                )
            )

    if lead_lag.classification.value == "leading":
        insights.append(
            Insight(
                title="인구가 통행량을 선행",
                detail=(
                    f"인구 변화가 통행량 변화를 약 {abs(lead_lag.best_lag_months)}개월 "
                    f"선행하는 패턴 (corr={lead_lag.best_correlation:+.2f})."
                ),
                score=round(abs(lead_lag.best_correlation), 4),
            )
        )
    elif lead_lag.classification.value == "lagging":
        insights.append(
            Insight(
                title="인구가 통행량을 후행",
                detail=(
                    f"통행량 증가가 인구 유입보다 {lead_lag.best_lag_months}개월 먼저 "
                    f"발생 (corr={lead_lag.best_correlation:+.2f})."
                ),
                score=round(abs(lead_lag.best_correlation), 4),
            )
        )

    if points:
        first, last = points[0], points[-1]
        if last.aadt and first.aadt and first.aadt > 0:
            growth = (last.aadt - first.aadt) / first.aadt
            insights.append(
                Insight(
                    title=f"통행량 누적 변화 {growth:+.1%}",
                    detail=(
                        f"{first.year_month} → {last.year_month}: "
                        f"{first.aadt:,.0f} → {last.aadt:,.0f} 대/일"
                    ),
                    score=round(min(abs(growth), 1.0), 4),
                )
            )

    return insights


def _confidence(points: list[TimePoint]) -> float:
    """Confidence saturates at 0.90 with 60+ months of data."""
    if not points:
        return 0.0
    base = 0.30
    cap = 0.90
    scale = min(len(points), 60) / 60.0
    return round(base + (cap - base) * scale, 3)


def _top_factors(
    corr: CorrelationMatrix,
    lead_lag: LeadLagAnalysis,
) -> list[dict[str, Any]]:
    factors: list[dict[str, Any]] = []

    pairs = [("road_progress", "population"), ("road_progress", "aadt"),
             ("population", "aadt")]
    for a, b in pairs:
        if a in corr.variables and b in corr.variables:
            c = corr.get(a, b)
            factors.append({
                "factor": f"corr({a},{b})",
                "value": c,
                "impact": "positive" if c > 0 else "negative",
                "explanation": f"{a} 와 {b}의 Pearson 상관계수.",
            })
    factors.append({
        "factor": "lead_lag(population,aadt)",
        "value": lead_lag.best_lag_months,
        "impact": (
            "neutral" if lead_lag.classification.value == "coincident" else "positive"
        ),
        "explanation": (
            f"인구→통행량 최적 시차 {lead_lag.best_lag_months}개월 "
            f"({lead_lag.classification.value})."
        ),
    })
    factors.sort(
        key=lambda f: abs(f["value"]) if isinstance(f["value"], int | float) else 0,
        reverse=True,
    )
    return factors[:3]
