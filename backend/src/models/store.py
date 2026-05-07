"""Scenario C — StoreBrand and Store.

A ``Store`` is one physical location (e.g. 스타벅스 김포공항DT). Multiple
stores can belong to one brand. A store points at a building via PNU.
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
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin
from src.models.enums import BRAND_CATEGORY, STORE_TYPE

if TYPE_CHECKING:
    from src.models.building import Building
    from src.models.impact import StoreImpactAnalysis
    from src.models.store_feature import StoreFeature


class StoreBrand(Base, TimestampMixin):
    """One row per brand (Starbucks, McDonald's, Burger King, …)."""

    __tablename__ = "store_brands"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    name_en: Mapped[str | None] = mapped_column(String(100), nullable=True)
    category: Mapped[str] = mapped_column(BRAND_CATEGORY, nullable=False)
    country: Mapped[str | None] = mapped_column(String(10), nullable=True)

    homepage: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    stores: Mapped[list[Store]] = relationship(
        back_populates="brand",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("name", name="uq_store_brands_name"),
        Index("ix_store_brands_category", "category"),
    )


class Store(Base, TimestampMixin):
    """One DT/DI/standard store."""

    __tablename__ = "stores"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    brand_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("store_brands.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # External identifier from the source page (brand-internal store code).
    source_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    region_code: Mapped[str | None] = mapped_column(
        String(10),
        ForeignKey("admin_areas.code", ondelete="SET NULL"),
        nullable=True,
    )
    location: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=False),
        nullable=True,
    )
    pnu: Mapped[str | None] = mapped_column(
        String(19),
        ForeignKey("buildings.pnu", ondelete="SET NULL"),
        nullable=True,
    )

    store_type: Mapped[str] = mapped_column(STORE_TYPE, nullable=False)

    # Lifecycle
    purchase_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    construction_approval_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    opened_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    closed_at: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Land / building snapshot at open
    land_area_m2: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    building_area_m2: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)

    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # ─── Relationships ───────────────────────────────────────────────────
    brand: Mapped[StoreBrand] = relationship(back_populates="stores")
    building: Mapped[Building | None] = relationship(back_populates="stores")
    features: Mapped[list[StoreFeature]] = relationship(
        back_populates="store",
        cascade="all, delete-orphan",
        order_by="StoreFeature.snapshot_date.desc()",
    )
    impact_analyses: Mapped[list[StoreImpactAnalysis]] = relationship(
        back_populates="store",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            "brand_id", "source_id",
            name="uq_stores_brand_source_id",
        ),
        Index("ix_stores_brand_id", "brand_id"),
        Index("ix_stores_pnu", "pnu"),
        Index("ix_stores_region_code", "region_code"),
        Index("ix_stores_store_type", "store_type"),
        Index("ix_stores_opened_at", "opened_at"),
        Index("gix_stores_location", "location", postgresql_using="gist"),
    )
