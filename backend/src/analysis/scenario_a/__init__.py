"""Scenario A — 보상금 영향 분석 (compensation impact regression)."""

from src.analysis.scenario_a.compensation_model import (
    CompensationImpactModel,
    DistanceTimePoint,
    ImpactPrediction,
    ImpactSeries,
)
from src.analysis.scenario_a.impact_zone import (
    ImpactZone,
    ImpactZoneExtractor,
    ImpactZoneRow,
)
from src.analysis.scenario_a.road_impact import (
    RoadImpactAnalyzer,
    RoadImpactRow,
)

__all__ = [
    "CompensationImpactModel",
    "DistanceTimePoint",
    "ImpactPrediction",
    "ImpactSeries",
    "ImpactZone",
    "ImpactZoneExtractor",
    "ImpactZoneRow",
    "RoadImpactAnalyzer",
    "RoadImpactRow",
]

MODEL_VERSION = "scenario_a_v1.0.0"
