"""Generate natural-language rationales for Scenario C predictions.

The generator inspects feature values + (optional) SHAP contributions and
returns a list of :class:`Rationale` objects, each tagged with a
``category`` and ``impact``. Rules are intentionally simple — Phase 2
will tune thresholds via offline calibration.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from src.analysis.scenario_c.feature_engineering import FeatureVector


class RationaleCategory(str, Enum):
    """Top-level grouping displayed in the UI."""

    PROPERTY = "property"
    SURROUNDINGS = "surroundings"
    TRAFFIC = "traffic"
    CATALYST = "catalyst"


class RationaleImpact(str, Enum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


@dataclass(slots=True, frozen=True)
class Rationale:
    """One rationale bullet for the API."""

    category: RationaleCategory
    impact: RationaleImpact
    feature: str
    value: float
    detail: str


# Ordered rule set. Each tuple is (category, impact, threshold-fn, message-fn).
# (Kept as a comment — the actual rules live inline in :meth:`generate`.)


class RationaleGenerator:
    """Threshold-based rule engine."""

    def __init__(self, *, max_per_category: int = 2) -> None:
        self._max_per_category = max_per_category

    def generate(
        self,
        vec: FeatureVector,
        *,
        shap_contributions: list[dict[str, Any]] | None = None,
    ) -> list[Rationale]:
        rationales: list[Rationale] = []
        v = vec.values

        # ─── Property ───────────────────────────────────────────────────
        if v.get("land_area_m2", 0) >= 1_500:
            rationales.append(self._mk(
                RationaleCategory.PROPERTY, RationaleImpact.POSITIVE,
                "land_area_m2", v["land_area_m2"],
                f"부지 {v['land_area_m2']:.0f}㎡ — 드라이브스루 진출입에 충분.",
            ))
        elif 0 < v.get("land_area_m2", 0) < 600:
            rationales.append(self._mk(
                RationaleCategory.PROPERTY, RationaleImpact.NEGATIVE,
                "land_area_m2", v["land_area_m2"],
                f"부지 {v['land_area_m2']:.0f}㎡ — 표준 매장도 빡빡할 수 있음.",
            ))
        if v.get("land_price_5y_growth", 0) >= 0.30:
            rationales.append(self._mk(
                RationaleCategory.PROPERTY, RationaleImpact.POSITIVE,
                "land_price_5y_growth", v["land_price_5y_growth"],
                f"5년 공시지가 {v['land_price_5y_growth']:+.1%} 상승 — 자산 가치 상승세.",
            ))

        # ─── Surroundings ──────────────────────────────────────────────
        pop_3km = v.get("population_within_3km", 0)
        if pop_3km >= 50_000:
            rationales.append(self._mk(
                RationaleCategory.SURROUNDINGS, RationaleImpact.POSITIVE,
                "population_within_3km", pop_3km,
                f"3km 이내 인구 {pop_3km:,.0f}명 — 충분한 배후 수요.",
            ))
        elif pop_3km < 10_000:
            rationales.append(self._mk(
                RationaleCategory.SURROUNDINGS, RationaleImpact.NEGATIVE,
                "population_within_3km", pop_3km,
                f"3km 이내 인구 {pop_3km:,.0f}명 — 배후 수요 부족.",
            ))
        comp_500m = v.get("competitor_count_within_500m", 0)
        if comp_500m >= 4:
            rationales.append(self._mk(
                RationaleCategory.SURROUNDINGS, RationaleImpact.NEGATIVE,
                "competitor_count_within_500m", comp_500m,
                f"500m 내 경쟁 매장 {int(comp_500m)}개 — 경쟁 강도 높음.",
            ))
        elif comp_500m == 0:
            rationales.append(self._mk(
                RationaleCategory.SURROUNDINGS, RationaleImpact.POSITIVE,
                "competitor_count_within_500m", comp_500m,
                "500m 내 경쟁 매장 없음 — 선점 효과 기대.",
            ))

        # ─── Traffic ───────────────────────────────────────────────────
        aadt = v.get("aadt_nearest_road", 0)
        if aadt >= 15_000:
            rationales.append(self._mk(
                RationaleCategory.TRAFFIC, RationaleImpact.POSITIVE,
                "aadt_nearest_road", aadt,
                f"인접 도로 AADT {aadt:,.0f} — 통행량이 충분.",
            ))
        elif 0 < aadt < 5_000:
            rationales.append(self._mk(
                RationaleCategory.TRAFFIC, RationaleImpact.NEGATIVE,
                "aadt_nearest_road", aadt,
                f"인접 도로 AADT {aadt:,.0f} — 통행량이 낮음.",
            ))
        dist = v.get("distance_to_nearest_road_m", 9999)
        if dist <= 50:
            rationales.append(self._mk(
                RationaleCategory.TRAFFIC, RationaleImpact.POSITIVE,
                "distance_to_nearest_road_m", dist,
                f"간선 도로 {dist:.0f}m 이내 — 접근성 우수.",
            ))
        elif dist > 500:
            rationales.append(self._mk(
                RationaleCategory.TRAFFIC, RationaleImpact.NEGATIVE,
                "distance_to_nearest_road_m", dist,
                f"간선 도로 {dist:.0f}m 거리 — 접근성 저하.",
            ))

        # ─── Catalysts ─────────────────────────────────────────────────
        if v.get("nearby_road_expansion", 0) >= 1:
            rationales.append(self._mk(
                RationaleCategory.CATALYST, RationaleImpact.POSITIVE,
                "nearby_road_expansion", v["nearby_road_expansion"],
                "최근 3년 내 인근 도로 확장 완료 — 통행량 증가 가능성.",
            ))
        if v.get("nearby_new_town", 0) >= 1:
            rationales.append(self._mk(
                RationaleCategory.CATALYST, RationaleImpact.POSITIVE,
                "nearby_new_town", v["nearby_new_town"],
                "인접 신도시·공공주택지구 지정 — 중기 인구 유입 호재.",
            ))
        growth = v.get("population_growth_3y_pct", 0)
        if growth >= 0.05:
            rationales.append(self._mk(
                RationaleCategory.CATALYST, RationaleImpact.POSITIVE,
                "population_growth_3y_pct", growth,
                f"3년 인구 {growth:+.1%} 성장 — 수요 확장 중.",
            ))
        elif growth < -0.02:
            rationales.append(self._mk(
                RationaleCategory.CATALYST, RationaleImpact.NEGATIVE,
                "population_growth_3y_pct", growth,
                f"3년 인구 {growth:+.1%} 감소 — 수요 위축.",
            ))

        # SHAP-driven extras: append any feature with |SHAP| in the top
        # contributors that isn't already covered by a threshold rule.
        if shap_contributions:
            already = {r.feature for r in rationales}
            for c in shap_contributions:
                if c["factor"] in already:
                    continue
                impact = (
                    RationaleImpact.POSITIVE
                    if c.get("impact") == "positive"
                    else RationaleImpact.NEGATIVE
                )
                rationales.append(
                    Rationale(
                        category=_category_for(c["factor"]),
                        impact=impact,
                        feature=c["factor"],
                        value=float(c.get("value", 0.0)),
                        detail=(
                            f"모델이 '{c['factor']}'를 핵심 요인으로 식별 "
                            f"(영향: {impact.value})."
                        ),
                    )
                )

        # Cap per category so the UI doesn't get spammed by one signal.
        return _trim_per_category(rationales, self._max_per_category)

    @staticmethod
    def _mk(
        category: RationaleCategory,
        impact: RationaleImpact,
        feature: str,
        value: float,
        detail: str,
    ) -> Rationale:
        return Rationale(
            category=category,
            impact=impact,
            feature=feature,
            value=float(value),
            detail=detail,
        )


def _category_for(feature: str) -> RationaleCategory:
    if feature.startswith(("land_", "building_", "is_", "floor_")):
        return RationaleCategory.PROPERTY
    if feature.startswith(("population_", "competitor_", "household", "office_",
                            "same_brand_", "transit_")):
        return RationaleCategory.SURROUNDINGS
    if feature.startswith(("aadt_", "distance_to_", "drive_thru_")):
        return RationaleCategory.TRAFFIC
    return RationaleCategory.CATALYST


def _trim_per_category(
    rationales: list[Rationale], cap: int
) -> list[Rationale]:
    seen: dict[RationaleCategory, int] = {}
    out: list[Rationale] = []
    for r in rationales:
        n = seen.get(r.category, 0)
        if n < cap:
            out.append(r)
            seen[r.category] = n + 1
    return out
