"""Pydantic schemas for the v1 analysis / prediction / recommendation surface."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ─── Reusable building blocks ───────────────────────────────────────────────


class FactorEntry(BaseModel):
    """One contributing factor row (used by every analysis envelope)."""

    factor: str
    value: Any
    impact: Literal["positive", "negative", "neutral"] = "neutral"
    explanation: str | None = None


class AnalysisMeta(BaseModel):
    """Common meta fields surfaced through the response envelope."""

    model_config = ConfigDict(extra="allow")

    model_version: str
    confidence_score: float = Field(ge=0.0, le=1.0)
    computation_time_ms: float | None = None
    top_factors: list[FactorEntry] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


# ─── Scenario A ─────────────────────────────────────────────────────────────


class ScenarioARequest(BaseModel):
    """Input for ``POST /api/v1/analysis/scenario-a``."""

    project_id: int = Field(ge=1)
    distances_m: list[float] | None = None
    horizons_months: list[int] | None = None
    radius_m: float = Field(default=5_000.0, ge=500.0, le=20_000.0)


class ScenarioAImpactPoint(BaseModel):
    distance_m: float
    months_after_anchor: int
    expected_uplift_pct: float
    confidence: float


class ScenarioAImpactSeries(BaseModel):
    distance_m: float
    points: list[ScenarioAImpactPoint]


class ScenarioAZone(BaseModel):
    admin_code: str
    admin_name: str
    distance_m: float


class ScenarioARoad(BaseModel):
    road_id: int
    name: str
    route_no: str | None = None
    length_m: float | None = None
    distance_m: float
    weight: float


class ScenarioAResponse(BaseModel):
    project_id: int
    anchor_date: date
    impact_series: list[ScenarioAImpactSeries]
    zones: list[ScenarioAZone]
    roads: list[ScenarioARoad]


# ─── Scenario B ─────────────────────────────────────────────────────────────


class ScenarioBRequest(BaseModel):
    road_id: int = Field(ge=1)
    start: date | None = None
    end: date | None = None


class ScenarioBTimePoint(BaseModel):
    year_month: str
    population: float | None
    aadt: float | None
    road_progress: float


class ScenarioBLeadLag(BaseModel):
    a: str
    b: str
    best_lag_months: int
    best_correlation: float
    classification: Literal["leading", "coincident", "lagging", "uncertain"]


class ScenarioBInsight(BaseModel):
    title: str
    detail: str
    score: float


class ScenarioBResponse(BaseModel):
    road_id: int
    time_points: list[ScenarioBTimePoint]
    correlation_variables: list[str]
    correlation_matrix: list[list[float]]
    lead_lag: ScenarioBLeadLag | None
    insights: list[ScenarioBInsight]


# ─── Scenario C ─────────────────────────────────────────────────────────────


class StoreImpactRequest(BaseModel):
    store_id: int = Field(ge=1)
    bands_m: list[int] | None = Field(
        default=None,
        description="Distance bands in meters (default 500/1000/2000/3000)",
    )


class StoreImpactBand(BaseModel):
    band_m: int
    horizon: Literal["+1y", "+3y", "+5y"]
    pre_avg_price_per_m2: float | None
    post_avg_price_per_m2: float | None
    change_pct: float | None
    baseline_pct: float | None
    halo_pct: float | None
    sample_pre: int
    sample_post: int


class StoreImpactResponse(BaseModel):
    store_id: int
    open_date: date
    bands: list[StoreImpactBand]


class LandSuitabilityRequest(BaseModel):
    pnu: str | None = None
    lat: float | None = None
    lng: float | None = None
    target: Literal["DT", "DI"] = "DT"
    snapshot_date: date | None = None


class LandSuitabilityResponse(BaseModel):
    pnu: str | None
    target: Literal["DT", "DI"]
    score_raw: float
    score_100: int
    label: Literal["low", "medium", "high"]
    rationales: list[dict[str, Any]]
    value_forecast: dict[str, float] | None = None


class DTCandidatesRequest(BaseModel):
    region_code: str = Field(min_length=2, max_length=10)
    target: Literal["DT", "DI"] = "DT"
    top_n: int = Field(default=10, ge=1, le=50)


class DTCandidatesResponse(BaseModel):
    region_code: str
    target: Literal["DT", "DI"]
    candidates: list[dict[str, Any]]


# ─── Recommendations ────────────────────────────────────────────────────────


class RecommendationsRequest(BaseModel):
    source_entity_type: Literal["region", "store"] = "region"
    source_entity_id: str
    top_n: int = Field(default=10, ge=1, le=50)


class RecommendationItemModel(BaseModel):
    target_entity_type: str
    target_entity_id: str
    target_label: str | None = None
    score: float
    rank: int
    breakdown: dict[str, Any] = Field(default_factory=dict)


class RecommendationsResponse(BaseModel):
    source_entity_type: str
    source_entity_id: str
    items: list[RecommendationItemModel]
