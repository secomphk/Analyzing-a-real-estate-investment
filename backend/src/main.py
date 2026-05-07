"""FastAPI application entrypoint.

Wires together:
* CORS + Prometheus instrumentation + (optional) Sentry
* Structured logging with per-request ``request_id``
* Request-time middleware (``X-Process-Time`` header) and slowapi rate limiting
* Lifespan: build the ML model registry, dispose engine + Redis on shutdown
* Global exception handlers that produce the project envelope
* ``/health`` readiness probe and the v1 router under ``/api/v1``
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

import sentry_sdk
from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from sentry_sdk.integrations.asgi import SentryAsgiMiddleware
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from src.api.v1.router import api_router
from src.core.config import get_settings
from src.core.database import dispose_engine
from src.core.exceptions import register_exception_handlers
from src.core.logging import app_logger, configure_logging, request_id_ctx
from src.core.redis_client import close_redis, ping_redis
from src.ml.registry import ModelRegistry, build_registry

settings = get_settings()

# ─── Sentry (optional) ──────────────────────────────────────────────────────
if settings.sentry_dsn and not settings.is_test:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment.value,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        release=settings.version,
    )

# ─── Rate limiter ───────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=[settings.rate_limit_default])


# ─── Lifespan ───────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup: configure logging, build model registry, preload models.

    Shutdown: drop model refs, close DB engine + Redis pool. Lifespan errors
    bubble up so a misconfigured environment fails fast at boot.
    """
    configure_logging()
    app_logger.info(
        "app_starting",
        environment=settings.environment.value,
        version=settings.version,
    )

    registry: ModelRegistry = build_registry()
    # Best-effort preload — if artifacts aren't published yet, the app still
    # boots; ``Depends(get_model(...))`` will raise 503 on demand.
    registry.preload(
        [
            ("suitability_dt", "v1"),
            ("suitability_di", "v1"),
            ("faiss_index", "v1"),
        ]
    )
    app.state.model_registry = registry
    app.state.started_at = time.time()

    app_logger.info("app_ready", loaded_models=registry.list_loaded())
    try:
        yield
    finally:
        app_logger.info("app_shutting_down")
        registry.unload_all()
        await close_redis()
        await dispose_engine()
        app_logger.info("app_shutdown_complete")


# ─── App factory ────────────────────────────────────────────────────────────


def create_app() -> FastAPI:
    """Build and configure the FastAPI app. Called once at module load."""
    app = FastAPI(
        title=settings.project_name,
        version=settings.version,
        description=(
            "Real Estate Investment Analysis Platform. "
            "Scenarios: A) compensation impact, B) road × population × traffic, "
            "C) DT/DI store siting."
        ),
        openapi_url=f"{settings.api_v1_prefix}/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # CORS — applied first so preflight requests aren't blocked by other middleware.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Rate limiting (slowapi). Hooks into Starlette via its own middleware.
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)
    app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)  # type: ignore[arg-type]

    # Sentry ASGI middleware only when a DSN is configured.
    if settings.sentry_dsn and not settings.is_test:
        app.add_middleware(SentryAsgiMiddleware)

    # Custom middlewares: request-id + timing + access log.
    app.middleware("http")(_request_context_middleware)

    # Global exception handlers — produce the standard envelope.
    register_exception_handlers(app)

    # Routers.
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    # Health and root.
    _register_health_routes(app)

    # Prometheus — exposes /metrics. Only instrument once, after routes.
    Instrumentator(
        should_group_status_codes=True,
        excluded_handlers=["/metrics", "/health"],
    ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

    return app


# ─── Middlewares & handlers ────────────────────────────────────────────────


async def _request_context_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Per-request setup: request id + timing header + structured log line."""
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex
    token = request_id_ctx.set(rid)
    started = time.perf_counter()
    try:
        response = await call_next(request)
    finally:
        request_id_ctx.reset(token)
    elapsed = (time.perf_counter() - started) * 1_000
    response.headers["x-request-id"] = rid
    response.headers["x-process-time-ms"] = f"{elapsed:.2f}"
    app_logger.info(
        "http_request",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=round(elapsed, 2),
    )
    return response


async def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> Response:
    """Translate slowapi's exception into the project envelope."""
    from fastapi.responses import JSONResponse  # noqa: PLC0415 — local import to avoid cycles

    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "data": None,
            "meta": {"status_code": status.HTTP_429_TOO_MANY_REQUESTS},
            "error": {
                "code": "rate_limit_exceeded",
                "message": f"Rate limit exceeded: {exc.detail}",
            },
        },
    )


# ─── Health endpoints ──────────────────────────────────────────────────────


def _register_health_routes(app: FastAPI) -> None:
    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, Any]:
        return {
            "data": {
                "service": settings.project_name,
                "version": settings.version,
                "docs": "/docs",
            },
            "meta": {"environment": settings.environment.value},
            "error": None,
        }

    @app.get("/health", tags=["health"], summary="Liveness + readiness probe")
    async def health(request: Request) -> dict[str, Any]:
        """Return service health.

        Liveness is implicit (the process is running); readiness checks Redis
        and reports loaded models. The DB ping is intentionally omitted so a
        transient DB blip doesn't take the API container out of rotation —
        per-request DB ops surface their own errors.
        """
        registry: ModelRegistry | None = getattr(request.app.state, "model_registry", None)
        return {
            "data": {
                "status": "ok",
                "uptime_seconds": round(time.time() - request.app.state.started_at, 2),
                "redis_ok": await ping_redis(),
                "loaded_models": registry.list_loaded() if registry else [],
            },
            "meta": {
                "environment": settings.environment.value,
                "version": settings.version,
            },
            "error": None,
        }


app = create_app()
