"""Common API dependencies.

Re-exports session/cache providers and adds Stage 1 placeholders for the
authentication and ML-registry deps that route handlers will consume in
Stage 2/3. Keeping them centralised lets routers depend on a stable surface
while their implementations evolve.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated, Any

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.exceptions import ModelNotLoadedError
from src.core.redis_client import get_redis

# ─── Re-exported, typed aliases for routes ─────────────────────────────────

DbSession = Annotated[AsyncSession, Depends(get_db)]
"""Async SQLAlchemy session, scoped to one request."""


async def _redis_dep() -> AsyncGenerator[Any, None]:
    """Yield the shared Redis client (no per-request setup)."""
    yield get_redis()


RedisDep = Annotated[Any, Depends(_redis_dep)]
"""Async Redis client (typed ``Any`` to avoid leaking redis-py generics)."""


# ─── ML registry dep (Stage 3) ─────────────────────────────────────────────


def get_model(name: str, version: str = "latest") -> Any:
    """Return a dependency that yields a loaded ML model from ``app.state``.

    Usage in a route::

        @router.post("/predict")
        async def predict(model: Annotated[Any, Depends(get_model("suitability_dt", "v1"))]):
            ...

    Raises:
        ModelNotLoadedError: if the registry has no entry for ``(name, version)``.
            This becomes a 503 via the global handler.
    """

    def _dep(request: Request) -> Any:
        registry = getattr(request.app.state, "model_registry", None)
        if registry is None:
            raise ModelNotLoadedError(f"Model registry not initialised: {name}@{version}")
        model = registry.get(name, version)
        if model is None:
            raise ModelNotLoadedError(f"Model not loaded: {name}@{version}")
        return model

    return _dep


# ─── Auth (Phase 2 stub) ───────────────────────────────────────────────────


async def get_current_user() -> dict[str, Any]:
    """Resolve the current user. Stage 1: anonymous principal.

    TODO(Phase 2): JWT decode + DB lookup; raise 401 if missing/invalid.
    """
    return {"id": None, "anonymous": True}


CurrentUser = Annotated[dict[str, Any], Depends(get_current_user)]
