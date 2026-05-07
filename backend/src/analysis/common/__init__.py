"""Cross-scenario analysis utilities (geometry, time alignment, scoring)."""

from src.analysis.common.normalizer import (
    minmax_scale,
    safe_pct_change,
    standardize,
    zscore_clip,
)
from src.analysis.common.validators import (
    AnalysisInputError,
    require_non_empty,
    validate_coordinate,
    validate_date_range,
    validate_pnu,
)

__all__ = [
    "AnalysisInputError",
    "minmax_scale",
    "require_non_empty",
    "safe_pct_change",
    "standardize",
    "validate_coordinate",
    "validate_date_range",
    "validate_pnu",
    "zscore_clip",
]
