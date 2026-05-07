"""Administrative area master (시/도, 시/군/구, 읍/면/동).

Stored hierarchically with ``parent_code`` so a 동 row points at its 구.
``code`` is the 행정안전부 행정구역 코드 (e.g. ``41210`` for 김포시).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from geoalchemy2 import Geometry
from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin
from src.models.enums import ADMIN_LEVEL

if TYPE_CHECKING:
    from src.models.population import PopulationStat


class AdminArea(Base, TimestampMixin):
    """One row per administrative unit.

    The root rows (sido) have ``parent_code = NULL``. The chain is
    sido → sigungu → eupmyeondong.
    """

    __tablename__ = "admin_areas"

    code: Mapped[str] = mapped_column(String(10), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    level: Mapped[str] = mapped_column(ADMIN_LEVEL, nullable=False)
    parent_code: Mapped[str | None] = mapped_column(
        String(10),
        ForeignKey("admin_areas.code", ondelete="SET NULL"),
        nullable=True,
    )

    # Boundary polygon in EPSG:4326. Optional for sido-level rows where we
    # only need the centroid for distance heuristics.
    geometry: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326, spatial_index=False),
        nullable=True,
    )
    centroid: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=False),
        nullable=True,
    )

    # ─── Relationships ───────────────────────────────────────────────────
    parent: Mapped[AdminArea | None] = relationship(
        "AdminArea",
        remote_side="AdminArea.code",
        back_populates="children",
    )
    children: Mapped[list[AdminArea]] = relationship(
        "AdminArea",
        back_populates="parent",
        cascade="all",
    )
    population_stats: Mapped[list[PopulationStat]] = relationship(
        back_populates="admin_area",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_admin_areas_level", "level"),
        Index("ix_admin_areas_name_trgm", "name", postgresql_using="gin",
              postgresql_ops={"name": "gin_trgm_ops"}),
        Index("gix_admin_areas_geometry", "geometry", postgresql_using="gist"),
        Index("gix_admin_areas_centroid", "centroid", postgresql_using="gist"),
    )
