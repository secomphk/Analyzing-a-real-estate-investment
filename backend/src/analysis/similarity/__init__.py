"""Cross-scenario similarity / recommendation engine."""

from src.analysis.similarity.feature_extractor import (
    RegionFeatureExtractor,
    RegionFeatureVector,
)
from src.analysis.similarity.matcher import SimilarityMatcher, SimilarityWeight
from src.analysis.similarity.recommender import (
    RecommendationItem,
    Recommender,
    RecommenderResult,
)

__all__ = [
    "RecommendationItem",
    "Recommender",
    "RecommenderResult",
    "RegionFeatureExtractor",
    "RegionFeatureVector",
    "SimilarityMatcher",
    "SimilarityWeight",
]
