"""Integration tests that need a real PostgreSQL + PostGIS instance.

Uses testcontainers when Docker is available; otherwise, you can point
``REALESTATE_PG_DSN`` at any Postgres-with-PostGIS for a quick check.
The whole module is skipped when neither is reachable so unit-only runs
stay fast.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.models import (
    AdminArea,
    Base,
    Building,
    OfficialLandPrice,
    Project,
    ProjectStage,
    Store,
    StoreBrand,
)

ENV_DSN = "REALESTATE_PG_DSN"


def _have_docker() -> bool:
    try:
        import docker  # noqa: PLC0415
    except ImportError:
        return False
    try:
        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


def _resolve_dsn() -> str | None:
    """Return a Postgres DSN if one is reachable; else None to skip."""
    if (dsn := os.getenv(ENV_DSN)):
        return dsn
    if _have_docker():
        # Lazy import — only paid for when Docker is available.
        try:
            from testcontainers.postgres import PostgresContainer  # noqa: PLC0415
        except ImportError:
            return None
        # The container is started inside the fixture, not here.
        return "TESTCONTAINER"
    return None


pytestmark = pytest.mark.skipif(
    _resolve_dsn() is None,
    reason=(
        "Integration tests need PostgreSQL+PostGIS. Set "
        f"{ENV_DSN} or install Docker + testcontainers to enable."
    ),
)


@pytest_asyncio.fixture(scope="module")
async def engine() -> AsyncIterator[object]:
    dsn = _resolve_dsn()
    container = None
    if dsn == "TESTCONTAINER":
        from testcontainers.postgres import PostgresContainer  # noqa: PLC0415

        container = PostgresContainer("postgis/postgis:16-3.4")
        container.start()
        sync_dsn = container.get_connection_url()
        dsn = sync_dsn.replace("postgresql+psycopg2", "postgresql+asyncpg")
    assert isinstance(dsn, str)

    eng = create_async_engine(dsn, future=True)
    async with eng.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield eng
    finally:
        await eng.dispose()
        if container is not None:
            container.stop()


@pytest_asyncio.fixture
async def session(engine: object) -> AsyncIterator[AsyncSession]:
    Session = async_sessionmaker(engine, expire_on_commit=False)  # type: ignore[arg-type]
    async with Session() as s:
        yield s
        await s.rollback()


@pytest.mark.asyncio
async def test_admin_area_round_trip(session: AsyncSession) -> None:
    sido = AdminArea(code="41", name="경기도", level="sido")
    session.add(sido)
    await session.flush()
    fetched = (await session.execute(
        select(AdminArea).where(AdminArea.code == "41")
    )).scalar_one()
    assert fetched.name == "경기도"


@pytest.mark.asyncio
async def test_project_with_stages_cascade(session: AsyncSession) -> None:
    session.add(AdminArea(code="41280", name="김포시", level="sigungu"))
    project = Project(
        name="테스트 사업", project_type="public_housing",
        region_code="41280", source="test",
    )
    project.stages.append(
        ProjectStage(stage="announced", occurred_at=date(2024, 1, 1))
    )
    project.stages.append(
        ProjectStage(stage="designated", occurred_at=date(2024, 6, 1))
    )
    session.add(project)
    await session.flush()
    fetched = (await session.execute(
        select(Project).where(Project.name == "테스트 사업")
    )).scalar_one()
    assert len(fetched.stages) == 2

    await session.delete(fetched)
    await session.flush()
    remaining = (await session.execute(select(ProjectStage))).all()
    assert remaining == []


@pytest.mark.asyncio
async def test_postgis_distance_between_two_points(session: AsyncSession) -> None:
    """Sanity-check that PostGIS is loaded and distance calc works."""
    result = await session.execute(
        text(
            "SELECT ST_Distance("
            "  ST_SetSRID(ST_MakePoint(126.6534, 37.6517), 4326)::geography, "
            "  ST_SetSRID(ST_MakePoint(126.7341, 37.6062), 4326)::geography"
            ") AS dist_m"
        )
    )
    dist_m = result.scalar_one()
    # Two centroids ~7-9 km apart in 김포.
    assert 5_000 < dist_m < 12_000


@pytest.mark.asyncio
async def test_store_brand_unique_constraint(session: AsyncSession) -> None:
    session.add(StoreBrand(name="유니크커피", category="cafe", country="KR"))
    await session.flush()
    session.add(StoreBrand(name="유니크커피", category="cafe", country="KR"))
    with pytest.raises(Exception):  # IntegrityError flavor varies by driver
        await session.flush()
    await session.rollback()


@pytest.mark.asyncio
async def test_official_land_price_change_rate_storage(session: AsyncSession) -> None:
    pnu = "1" * 19
    session.add(Building(pnu=pnu, address="테스트", source="test"))
    session.add(OfficialLandPrice(pnu=pnu, year=2023, price_per_m2=1_000_000))
    session.add(OfficialLandPrice(
        pnu=pnu, year=2024, price_per_m2=1_080_000, change_rate=8.0
    ))
    await session.flush()
    rows = (await session.execute(
        select(OfficialLandPrice).where(OfficialLandPrice.pnu == pnu)
        .order_by(OfficialLandPrice.year)
    )).scalars().all()
    assert [r.year for r in rows] == [2023, 2024]
    assert float(rows[1].change_rate) == 8.0
