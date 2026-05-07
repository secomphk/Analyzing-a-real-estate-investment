"""Scenario B — RoadSegment + RoadExpansionStage.

A road expansion event is recorded as a stage row pointing back at the
segment, mirroring the project/stage pattern.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin
from src.models.enums import ROAD_STAGE_KIND

if TYPE_CHECKING:
    from src.models.traffic import TrafficVolume


class RoadSegment(Base, TimestampMixin):
    """One contiguous road we are tracking (e.g. 평택 만세로 일부 구간)."""

    __tablename__ = "road_segments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    route_no: Mapped[str | None] = mapped_column(String(50), nullable=True)
    region_code: Mapped[str | None] = mapped_column(
        String(10),
        ForeignKey("admin_areas.code", ondelete="SET NULL"),
        nullable=True,
    )

    # LineString of the centerline.
    geometry: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="LINESTRING", srid=4326, spatial_index=False),
        nullable=True,
    )
    length_m: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    raw_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    stages: Mapped[list[RoadExpansionStage]] = relationship(
        back_populates="road",
        cascade="all, delete-orphan",
        order_by="RoadExpansionStage.occurred_at",
    )
    traffic_volumes: Mapped[list[TrafficVolume]] = relationship(
        back_populates="road",
        cascade="all, delete-orphan",
        order_by="TrafficVolume.observed_at",
    )

    __table_args__ = (
        UniqueConstraint("name", "route_no", name="uq_road_segments_name_route"),
        Index("ix_road_segments_region_code", "region_code"),
        Index("gix_road_segments_geometry", "geometry", postgresql_using="gist"),
    )


class RoadExpansionStage(Base, TimestampMixin):
    """Lifecycle stage for one road expansion (planned → completed)."""

    __tablename__ = "road_expansion_stages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    road_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("road_segments.id", ondelete="CASCADE"),
        nullable=False,
    )
    stage: Mapped[str] = mapped_column(ROAD_STAGE_KIND, nullable=False)
    occurred_at: Mapped[date] = mapped_column(Date, nullable=False)

    lanes_before: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lanes_after: Mapped[int | None] = mapped_column(Integer, nullable=True)
    width_before_m: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    width_after_m: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)

    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    raw_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    road: Mapped[RoadSegment] = relationship(back_populates="stages")

    __table_args__ = (
        UniqueConstraint(
            "road_id", "stage", "occurred_at",
            name="uq_road_expansion_stages_road_stage_date",
        ),
        Index("ix_road_expansion_stages_road_id", "road_id"),
        Index("ix_road_expansion_stages_occurred_at", "occurred_at"),
    )
