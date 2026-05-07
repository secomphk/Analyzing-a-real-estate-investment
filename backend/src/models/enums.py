"""PostgreSQL ENUM types shared across the schema.

We use ``str``-backed Python enums and let SQLAlchemy emit a proper
``CREATE TYPE`` so the values are validated at the DB level too. The
``create_type=False`` flag on column-level usages avoids duplicate
``CREATE TYPE`` statements when several tables reference the same enum.
"""

from __future__ import annotations

from enum import Enum

from sqlalchemy import Enum as SAEnum


class ProjectType(str, Enum):
    """Type of 호재 (development project)."""

    PUBLIC_HOUSING = "public_housing"        # 공공주택지구
    URBAN_DEVELOPMENT = "urban_development"  # 도시개발
    INDUSTRIAL_COMPLEX = "industrial_complex"
    LOGISTICS = "logistics"
    NEW_TOWN = "new_town"                    # 신도시
    OTHER = "other"


class ProjectStageKind(str, Enum):
    """Lifecycle stages of a development project (PRD §4.2)."""

    PLANNED = "planned"
    ANNOUNCED = "announced"                  # 지구지정 공고
    DESIGNATED = "designated"                # 지구지정 확정
    COMPENSATION_PLANNED = "compensation_planned"
    COMPENSATION_STARTED = "compensation_started"
    RELOCATION_COMPLETE = "relocation_complete"
    GROUND_BREAK = "ground_break"            # 착공
    UNDER_CONSTRUCTION = "under_construction"
    COMPLETION = "completion"                # 준공


class AdminLevel(str, Enum):
    """Administrative hierarchy level."""

    SIDO = "sido"                            # 시·도
    SIGUNGU = "sigungu"                      # 시·군·구
    EUPMYEONDONG = "eupmyeondong"            # 읍·면·동


class TransactionType(str, Enum):
    """Real-estate transaction product type."""

    LAND = "land"                            # 토지
    APARTMENT = "apartment"                  # 아파트
    OFFICETEL = "officetel"
    SINGLE_HOUSE = "single_house"            # 단독·다가구
    COMMERCIAL = "commercial"                # 상가·업무용
    OTHER = "other"


class RoadStageKind(str, Enum):
    """Road expansion lifecycle."""

    PLANNED = "planned"
    DESIGN = "design"
    UNDER_CONSTRUCTION = "under_construction"
    COMPLETED = "completed"


class StoreType(str, Enum):
    """매장 형태."""

    DT = "DT"                                # Drive-Thru
    DI = "DI"                                # Drive-In
    STANDARD = "standard"                    # 일반 매장
    KIOSK = "kiosk"


class BrandCategory(str, Enum):
    """Store brand category."""

    CAFE = "cafe"
    FASTFOOD = "fastfood"
    BAKERY = "bakery"
    CONVENIENCE = "convenience"
    OTHER = "other"


class AnalysisScenario(str, Enum):
    """Top-level analysis scenario."""

    A = "a"  # 보상금 영향
    B = "b"  # 도로 × 인구 × 통행량
    C = "c"  # DT/DI 입지


class AnalysisStatus(str, Enum):
    """Analysis run status."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


# ─── Re-usable SAEnum factories ─────────────────────────────────────────────
# All enums are created exactly once (via the migration); subsequent column
# definitions reference them with ``create_type=False`` to avoid duplicate
# CREATE TYPE statements during table creation.

def pg_enum(enum_cls: type[Enum], *, name: str, create_type: bool = False) -> SAEnum:
    """Build a ``Enum`` SQLAlchemy column type bound to a PG ENUM."""
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=True,
        create_type=create_type,
        validate_strings=True,
        values_callable=lambda e: [m.value for m in e],
    )


PROJECT_TYPE = pg_enum(ProjectType, name="project_type")
PROJECT_STAGE_KIND = pg_enum(ProjectStageKind, name="project_stage_kind")
ADMIN_LEVEL = pg_enum(AdminLevel, name="admin_level")
TRANSACTION_TYPE = pg_enum(TransactionType, name="transaction_type")
ROAD_STAGE_KIND = pg_enum(RoadStageKind, name="road_stage_kind")
STORE_TYPE = pg_enum(StoreType, name="store_type")
BRAND_CATEGORY = pg_enum(BrandCategory, name="brand_category")
ANALYSIS_SCENARIO = pg_enum(AnalysisScenario, name="analysis_scenario")
ANALYSIS_STATUS = pg_enum(AnalysisStatus, name="analysis_status")
