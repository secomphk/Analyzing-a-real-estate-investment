"""Scenario C — DT/DI 매장 입지 예측 (XGBoost + FAISS + Prophet)."""

from src.analysis.scenario_c.candidate_finder import (
    CandidateFinder,
    CandidateRanking,
    CandidateRow,
)
from src.analysis.scenario_c.feature_engineering import (
    FEATURE_NAMES,
    FeatureExtractor,
    FeatureVector,
)
from src.analysis.scenario_c.impact_analyzer import (
    DistanceBandImpact,
    StoreImpactAnalyzer,
    StoreImpactResult,
)
from src.analysis.scenario_c.rationale_generator import (
    Rationale,
    RationaleCategory,
    RationaleGenerator,
    RationaleImpact,
)
from src.analysis.scenario_c.similarity_search import (
    StoreSimilarityIndex,
    StoreSimilarityResult,
)
from src.analysis.scenario_c.suitability_model import (
    Suitability,
    SuitabilityExplanation,
    SuitabilityModel,
)
from src.analysis.scenario_c.value_predictor import (
    LandValueForecast,
    LandValuePredictor,
)

__all__ = [
    "FEATURE_NAMES",
    "CandidateFinder",
    "CandidateRanking",
    "CandidateRow",
    "DistanceBandImpact",
    "FeatureExtractor",
    "FeatureVector",
    "LandValueForecast",
    "LandValuePredictor",
    "Rationale",
    "RationaleCategory",
    "RationaleGenerator",
    "RationaleImpact",
    "StoreImpactAnalyzer",
    "StoreImpactResult",
    "StoreSimilarityIndex",
    "StoreSimilarityResult",
    "Suitability",
    "SuitabilityExplanation",
    "SuitabilityModel",
]

MODEL_VERSION = "scenario_c_v1.0.0"
