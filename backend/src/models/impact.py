"""Scenario C — StoreImpactAnalysis (매장 입점 효과, halo by distance band).

For each store, we record one row per distance band (50m / 100m / 200m /
500m / ...). Pre/post averages are computed over a fixed window before
and after the open date.
"""

from __future__ import annotations

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


class StoreImpactAnalysis(Base, TimestampMixin):
    """Halo-effect metrics for one store at one distance band."""

    __tablename__ = "store_impact_analysis"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
    )
    distance_band_m: Mapped[int] = mapped_column(Integer, nullable=False)

    # Window definition (so the row stays interpretable after the underlying
    # transactions table changes).
    pre_window_start: Mapped[Any] = mapped_column(Date, nullable=False)
    pre_window_end: Mapped[Any] = mapped_column(Date, nullable=False)
    post_window_start: Mapped[Any] = mapped_column(Date, nullable=False)
    post_window_end: Mapped[Any] = mapped_column(Date, nullable=False)

    pre_open_avg_price_per_m2: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    post_open_avg_price_per_m2: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    change_rate: Mapped[float | None] = mapped_column(Numeric(7, 4), nullable=True)
    pre_sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    post_sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    extra: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    store: Mapped[Store] = relationship(back_populates="impact_analyses")

    __table_args__ = (
        UniqueConstraint(
            "store_id", "distance_band_m", "post_window_end",
            name="uq_store_impact_store_band_window",
        ),
        Index("ix_store_impact_store_id", "store_id"),
        Index("ix_store_impact_distance_band", "distance_band_m"),
    )
