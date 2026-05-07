"""Cross-scenario analysis result cache + recommendation table.

``AnalysisResult`` keys results by ``(scenario, entity_type, entity_id, params_hash)``
so identical requests can be served from cache. Long-form payload lives in
``result`` (JSONB).

``Recommendation`` is the persisted output of the similarity engine —
``(source, target, model_version)`` is unique.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin
from src.models.enums import ANALYSIS_SCENARIO, ANALYSIS_STATUS


class AnalysisResult(Base, TimestampMixin):
    """Cached output of one analysis run."""

    __tablename__ = "analysis_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    scenario: Mapped[str] = mapped_column(ANALYSIS_SCENARIO, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(100), nullable=False)
    params_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    status: Mapped[str] = mapped_column(
        ANALYSIS_STATUS, nullable=False, default="completed"
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "scenario", "entity_type", "entity_id", "params_hash",
            name="uq_analysis_results_scenario_entity_params",
        ),
        Index("ix_analysis_results_status", "status"),
        Index("ix_analysis_results_expires_at", "expires_at"),
    )


class Recommendation(Base, TimestampMixin):
    """Persisted similarity recommendation (one source → one target)."""

    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    source_entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_entity_id: Mapped[str] = mapped_column(String(100), nullable=False)
    target_entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_entity_id: Mapped[str] = mapped_column(String(100), nullable=False)

    score: Mapped[float] = mapped_column(Numeric(7, 4), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    model_version: Mapped[str] = mapped_column(String(20), nullable=False)

    extra: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "source_entity_type", "source_entity_id",
            "target_entity_type", "target_entity_id",
            "model_version",
            name="uq_recommendations_source_target_version",
        ),
        Index(
            "ix_recommendations_source",
            "source_entity_type", "source_entity_id", "rank",
        ),
    )
