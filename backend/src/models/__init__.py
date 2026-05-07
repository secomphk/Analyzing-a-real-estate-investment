"""SQLAlchemy ORM models.

Importing this package registers every table on ``Base.metadata`` —
critical for Alembic autogenerate and for ``Base.metadata.create_all``
in tests.
"""

from __future__ import annotations

from src.models.admin_area import AdminArea
from src.models.analysis import AnalysisResult, Recommendation
from src.models.base import Base, TimestampMixin
from src.models.building import Building
from src.models.candidate import CandidateLand
from src.models.impact import StoreImpactAnalysis
from src.models.land_price import OfficialLandPrice
from src.models.population import PopulationStat
from src.models.project import Project, ProjectStage
from src.models.road import RoadExpansionStage, RoadSegment
from src.models.store import Store, StoreBrand
from src.models.store_feature import StoreFeature
from src.models.traffic import TrafficVolume
from src.models.transaction import LandTransaction

__all__ = [
    "AdminArea",
    "AnalysisResult",
    "Base",
    "Building",
    "CandidateLand",
    "LandTransaction",
    "OfficialLandPrice",
    "PopulationStat",
    "Project",
    "ProjectStage",
    "Recommendation",
    "RoadExpansionStage",
    "RoadSegment",
    "Store",
    "StoreBrand",
    "StoreFeature",
    "StoreImpactAnalysis",
    "TimestampMixin",
    "TrafficVolume",
]
