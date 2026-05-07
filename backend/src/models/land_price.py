"""Scenario C — OfficialLandPrice (개별공시지가, annual).

One row per (parcel, year). Published every May for the prior reference
date (2024년 1월 1일 기준 공시지가 → 2024년 5월 발표).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import (
    BigInteger,
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
from src.models.building import Building


class OfficialLandPrice(Base, TimestampMixin):
    """공시지가 — KRW per m², per year, per PNU."""

    __tablename__ = "official_land_prices"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pnu: Mapped[str] = mapped_column(
        String(19),
        ForeignKey("buildings.pnu", ondelete="CASCADE"),
        nullable=False,
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    price_per_m2: Mapped[int] = mapped_column(BigInteger, nullable=False)
    change_rate: Mapped[float | None] = mapped_column(Numeric(7, 4), nullable=True)

    source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    raw_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    building: Mapped[Building] = relationship(back_populates="land_prices")

    __table_args__ = (
        UniqueConstraint("pnu", "year", name="uq_official_land_prices_pnu_year"),
        Index("ix_official_land_prices_year", "year"),
    )
