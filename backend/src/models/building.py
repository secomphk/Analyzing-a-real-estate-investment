"""Scenario C — Building (건축물대장).

PNU (필지고유번호, 19 chars) is the natural primary key — it uniquely
identifies a parcel in the cadastral system and is the join key between
land prices, transactions, and stores.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

from geoalchemy2 import Geometry
from sqlalchemy import (
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.land_price import OfficialLandPrice
    from src.models.store import Store


class Building(Base, TimestampMixin):
    """One row per parcel-with-a-building (or vacant parcel)."""

    __tablename__ = "buildings"

    pnu: Mapped[str] = mapped_column(String(19), primary_key=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    region_code: Mapped[str | None] = mapped_column(
        String(10),
        ForeignKey("admin_areas.code", ondelete="SET NULL"),
        nullable=True,
    )

    # Cadastral / building metrics
    parcel_area_m2: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    building_area_m2: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    total_floor_area_m2: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    floors_above: Mapped[int | None] = mapped_column(Integer, nullable=True)
    floors_below: Mapped[int | None] = mapped_column(Integer, nullable=True)

    use_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    structure: Mapped[str | None] = mapped_column(String(100), nullable=True)
    approval_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    geometry: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326, spatial_index=False),
        nullable=True,
    )

    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    raw_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # ─── Relationships ───────────────────────────────────────────────────
    stores: Mapped[list[Store]] = relationship(
        back_populates="building",
        cascade="save-update",
    )
    land_prices: Mapped[list[OfficialLandPrice]] = relationship(
        back_populates="building",
        cascade="all, delete-orphan",
        order_by="OfficialLandPrice.year",
    )

    __table_args__ = (
        Index("ix_buildings_region_code", "region_code"),
        Index("ix_buildings_use_type", "use_type"),
        Index("ix_buildings_approval_date", "approval_date"),
        Index("gix_buildings_geometry", "geometry", postgresql_using="gist"),
    )
