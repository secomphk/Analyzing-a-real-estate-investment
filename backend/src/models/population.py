"""Scenario B — PopulationStat time-series.

행정안전부 주민등록 인구통계, 월별. Keyed by (region_code, observed_at).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import (
    BigInteger,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.admin_area import AdminArea
from src.models.base import Base, TimestampMixin


class PopulationStat(Base, TimestampMixin):
    """Resident population for an admin area on a given month-end."""

    __tablename__ = "population_stats"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    region_code: Mapped[str] = mapped_column(
        String(10),
        ForeignKey("admin_areas.code", ondelete="CASCADE"),
        nullable=False,
    )
    observed_at: Mapped[date] = mapped_column(Date, nullable=False)
    total_population: Mapped[int] = mapped_column(Integer, nullable=False)
    male_population: Mapped[int | None] = mapped_column(Integer, nullable=True)
    female_population: Mapped[int | None] = mapped_column(Integer, nullable=True)
    household_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    avg_age: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)

    source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    raw_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    admin_area: Mapped[AdminArea] = relationship(back_populates="population_stats")

    __table_args__ = (
        UniqueConstraint(
            "region_code", "observed_at",
            name="uq_population_stats_region_observed_at",
        ),
        Index("ix_population_stats_observed_at", "observed_at"),
    )
