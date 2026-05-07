"""Scenario B — TrafficVolume time-series.

One observation row per (road, observed_at). Granularity is typically
monthly (AADT averaged over the month) but the schema supports daily.
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

from src.models.base import Base, TimestampMixin
from src.models.road import RoadSegment


class TrafficVolume(Base, TimestampMixin):
    """Average daily traffic for a road on a given date."""

    __tablename__ = "traffic_volumes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    road_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("road_segments.id", ondelete="CASCADE"),
        nullable=False,
    )
    observed_at: Mapped[date] = mapped_column(Date, nullable=False)
    aadt: Mapped[int] = mapped_column(Integer, nullable=False)         # vehicles/day
    peak_hour_volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    heavy_vehicle_pct: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)

    source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    raw_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    road: Mapped[RoadSegment] = relationship(back_populates="traffic_volumes")

    __table_args__ = (
        UniqueConstraint(
            "road_id", "observed_at",
            name="uq_traffic_volumes_road_observed_at",
        ),
        Index("ix_traffic_volumes_observed_at", "observed_at"),
    )
