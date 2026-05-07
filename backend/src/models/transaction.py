"""Real-estate transactions (MOLIT 실거래가).

Used by all three scenarios: Scenario A as the price observation, Scenario B
as a control, Scenario C for halo-effect impact analysis around stores.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from geoalchemy2 import Geometry
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
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin
from src.models.enums import TRANSACTION_TYPE


class LandTransaction(Base, TimestampMixin):
    """One observed MOLIT transaction.

    ``source_id`` is the MOLIT-assigned hash of (시군구, 거래연월, 일련번호)
    — used for idempotent UPSERTs.
    """

    __tablename__ = "land_transactions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # External identifier — UNIQUE so re-running the ETL is idempotent.
    source_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="molit")

    # Locality
    region_code: Mapped[str] = mapped_column(
        String(10),
        ForeignKey("admin_areas.code", ondelete="SET NULL"),
        nullable=True,
    )
    pnu: Mapped[str | None] = mapped_column(String(19), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=False),
        nullable=True,
    )

    # Deal
    transaction_type: Mapped[str] = mapped_column(TRANSACTION_TYPE, nullable=False)
    contract_date: Mapped[date] = mapped_column(Date, nullable=False)
    deal_amount_krw: Mapped[int] = mapped_column(BigInteger, nullable=False)
    area_m2: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    floor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    use_district: Mapped[str | None] = mapped_column(String(50), nullable=True)

    raw_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        UniqueConstraint("source_id", name="uq_land_transactions_source_id"),
        Index("ix_land_transactions_region_date", "region_code", "contract_date"),
        Index("ix_land_transactions_pnu", "pnu"),
        Index("ix_land_transactions_type_date", "transaction_type", "contract_date"),
        Index("gix_land_transactions_location", "location", postgresql_using="gist"),
    )
