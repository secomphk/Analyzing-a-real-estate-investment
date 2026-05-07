"""Scenario C — StoreFeature time-series.

A snapshot of the engineered feature vector for a store at a given date,
plus a free-form ``feature_vector`` (JSONB) for ad-hoc fields that don't
warrant a column. Used both as XGBoost training rows and as the source for
FAISS embedding builds.
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
from src.models.store import Store


class StoreFeature(Base, TimestampMixin):
    """Per-store, per-snapshot feature row."""

    __tablename__ = "store_features"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False, default="v1")

    # ─── Frequently-queried scalar features ─────────────────────────────
    population_within_1km: Mapped[int | None] = mapped_column(Integer, nullable=True)
    population_within_3km: Mapped[int | None] = mapped_column(Integer, nullable=True)
    aadt_nearest_road: Mapped[int | None] = mapped_column(Integer, nullable=True)
    distance_to_nearest_road_m: Mapped[float | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    competitor_count_within_1km: Mapped[int | None] = mapped_column(Integer, nullable=True)
    land_price_per_m2: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # ─── Catch-all for less-common features (sparse, evolving) ──────────
    feature_vector: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )

    store: Mapped[Store] = relationship(back_populates="features")

    __table_args__ = (
        UniqueConstraint(
            "store_id", "snapshot_date", "version",
            name="uq_store_features_store_date_version",
        ),
        Index("ix_store_features_snapshot_date", "snapshot_date"),
    )
