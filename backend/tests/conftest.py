"""Pytest configuration shared by every test module.

Sets ``ENVIRONMENT=test`` before any app code imports so Sentry, slowapi, and
model preloading skip work that needs external services. Provides a session
``httpx.AsyncClient`` bound to the FastAPI app via ``ASGITransport`` — no
actual TCP socket, so tests don't require Postgres or Redis to be up.
"""

from __future__ import annotations

import os

# Set BEFORE app import so `get_settings()` picks it up.
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("SENTRY_DSN", "")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")

from collections.abc import AsyncIterator  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402


@pytest.fixture(scope="session")
def app() -> FastAPI:
    """The application under test."""
    from src.main import app as fastapi_app

    return fastapi_app


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Async HTTP client wired to the ASGI app — no network, no DB."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        # Use lifespan-managed app state by triggering startup manually.
        async with app.router.lifespan_context(app):
            yield ac
