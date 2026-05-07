"""Async SQLAlchemy + GeoAlchemy2 wiring.

Single async engine + ``async_sessionmaker`` shared across the app. The
``get_db`` dependency yields one session per request and rolls back on
exception so partially-written state never leaks.

GeoAlchemy2 is imported once on module load — it registers PostGIS dialect
hooks so ``Geometry`` / ``Geography`` column types resolve correctly.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import geoalchemy2  # noqa: F401  (registers PostGIS types with SA dialects)
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.core.config import get_settings


def _build_engine() -> AsyncEngine:
    """Create the async engine using current settings."""
    settings = get_settings()
    return create_async_engine(
        str(settings.database_url),
        echo=settings.db_echo,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=settings.db_pool_pre_ping,
        future=True,
    )


engine: AsyncEngine = _build_engine()
"""Process-wide async engine. Lifespan handler disposes it at shutdown."""

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autoflush=False,
)
"""Factory used by ``get_db`` and any code that needs an ad-hoc session."""


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: open a session, roll back on error, always close.

    Usage::

        @router.get("/foo")
        async def foo(db: Annotated[AsyncSession, Depends(get_db)]) -> ...:
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def dispose_engine() -> None:
    """Close all pooled connections. Called from FastAPI lifespan shutdown."""
    await engine.dispose()
