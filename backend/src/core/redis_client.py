"""Async Redis client.

One connection pool per process, lazily initialized so importing the module
doesn't open sockets (matters for Alembic, tests, and `--help`).
"""

from __future__ import annotations

from typing import Any

import redis.asyncio as aioredis

from src.core.config import get_settings

# Typed as Any — redis-py's stubs make ``Redis`` generic in a way that
# pollutes every consumer with type parameters they don't care about.
_client: Any | None = None


def get_redis() -> Any:
    """Return the process-wide async Redis client (lazy)."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            health_check_interval=30,
        )
    return _client


async def close_redis() -> None:
    """Close the pool. Called from FastAPI lifespan shutdown."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def ping_redis() -> bool:
    """Health check: True if Redis answers PING. Never raises."""
    try:
        return bool(await get_redis().ping())
    except Exception:  # noqa: BLE001 — health checks must never raise
        return False
