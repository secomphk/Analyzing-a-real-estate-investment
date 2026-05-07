"""Scenario C — CandidateLand (후보 토지 적합도).

A scored row produced by the suitability model for a candidate parcel.
Many rows per PNU are allowed, distinguished by ``model_version`` so we
can compare model versions head-to-head.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin


class CandidateLand(Base, TimestampMixin):
    """Suitability score for one candidate parcel."""

    __tablename__ = "candidate_lands"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pnu: Mapped[str] = mapped_column(
        String(19),
        ForeignKey("buildings.pnu", ondelete="CASCADE"),
        nullable=False,
    )

    # Snapshot copy in case the building row is later deleted/updated.
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=False),
        nullable=True,
    )

    suitability_score: Mapped[float] = mapped_column(Numeric(7, 4), nullable=False)
    breakdown: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_version: Mapped[str] = mapped_column(String(20), nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "pnu", "model_name", "model_version", "evaluated_at",
            name="uq_candidate_lands_pnu_model_version_evaluated",
        ),
        Index("ix_candidate_lands_pnu", "pnu"),
        Index("ix_candidate_lands_score", "suitability_score"),
        Index("gix_candidate_lands_location", "location", postgresql_using="gist"),
    )
