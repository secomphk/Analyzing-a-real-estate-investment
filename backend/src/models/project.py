"""Scenario A/B — 호재 사업 (Project) and its lifecycle stages.

A ``Project`` is one development project (공공주택지구, 도시개발 등). Stages
are recorded as separate rows in ``project_stages`` so a project can have
multiple events (announced → designated → compensation_started → ...).
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
from src.models.enums import PROJECT_STAGE_KIND, PROJECT_TYPE

if TYPE_CHECKING:
    pass


class Project(Base, TimestampMixin):
    """Top-level development project record."""

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    project_type: Mapped[str] = mapped_column(PROJECT_TYPE, nullable=False)
    region_code: Mapped[str | None] = mapped_column(
        String(10),
        ForeignKey("admin_areas.code", ondelete="SET NULL"),
        nullable=True,
    )

    # Project polygon (boundary) — used for distance-band aggregation.
    geometry: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326, spatial_index=False),
        nullable=True,
    )
    centroid: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=False),
        nullable=True,
    )

    area_ha: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    expected_compensation_billion_krw: Mapped[float | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    planned_announcement_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    planned_completion_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    raw_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # ─── Relationships ───────────────────────────────────────────────────
    stages: Mapped[list[ProjectStage]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ProjectStage.occurred_at",
    )

    __table_args__ = (
        UniqueConstraint("name", "project_type", name="uq_projects_name_type"),
        Index("ix_projects_region_code", "region_code"),
        Index("ix_projects_type", "project_type"),
        Index("gix_projects_geometry", "geometry", postgresql_using="gist"),
        Index("gix_projects_centroid", "centroid", postgresql_using="gist"),
    )


class ProjectStage(Base, TimestampMixin):
    """One lifecycle event per row.

    A project can hit the same stage twice (e.g. planning revisions); the
    composite uniqueness uses ``(project_id, stage, occurred_at)``.
    """

    __tablename__ = "project_stages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    stage: Mapped[str] = mapped_column(PROJECT_STAGE_KIND, nullable=False)
    occurred_at: Mapped[date] = mapped_column(Date, nullable=False)
    sequence_no: Mapped[int | None] = mapped_column(Integer, nullable=True)

    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    raw_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    project: Mapped[Project] = relationship(back_populates="stages")

    __table_args__ = (
        UniqueConstraint(
            "project_id", "stage", "occurred_at",
            name="uq_project_stages_project_stage_date",
        ),
        Index("ix_project_stages_project_id", "project_id"),
        Index("ix_project_stages_occurred_at", "occurred_at"),
    )
