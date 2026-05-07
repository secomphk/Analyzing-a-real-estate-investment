"""Domain exceptions and global FastAPI exception handlers.

All handlers shape responses into the project-wide envelope:

    { "data": null, "meta": {...}, "error": {"code": "...", "message": "..."} }

This guarantees a single response contract regardless of where the failure
originated (route, validation, ORM, unexpected).
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.core.logging import get_logger

logger = get_logger("app.errors")


# ─── Domain exceptions ──────────────────────────────────────────────────────


class AppError(Exception):
    """Base class for app-level errors that map cleanly to HTTP responses."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code: str = "internal_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(AppError):
    """Resource lookup miss (e.g. project_id does not exist)."""

    status_code = status.HTTP_404_NOT_FOUND
    error_code = "not_found"


class ValidationError(AppError):
    """Domain-level validation failure (Pydantic 422 is handled separately)."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "validation_error"


class ConflictError(AppError):
    """Operation conflicts with current state (e.g. duplicate key)."""

    status_code = status.HTTP_409_CONFLICT
    error_code = "conflict"


class ExternalServiceError(AppError):
    """Upstream API (MOLIT, Kakao, Sentry, ...) returned an unrecoverable error."""

    status_code = status.HTTP_502_BAD_GATEWAY
    error_code = "external_service_error"


class ModelNotLoadedError(AppError):
    """Inference requested before the model is registered/loaded."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    error_code = "model_not_loaded"


# ─── Response envelope helper ───────────────────────────────────────────────


def _envelope(
    *,
    error_code: str,
    message: str,
    status_code: int,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    payload: dict[str, Any] = {
        "data": None,
        "meta": {"status_code": status_code},
        "error": {"code": error_code, "message": message},
    }
    if details:
        payload["error"]["details"] = details
    return JSONResponse(status_code=status_code, content=payload)


# ─── Handlers ───────────────────────────────────────────────────────────────


async def app_error_handler(_: Request, exc: Exception) -> JSONResponse:
    """Handle any ``AppError`` subclass."""
    assert isinstance(exc, AppError)
    logger.warning(
        "app_error",
        error_code=exc.error_code,
        status_code=exc.status_code,
        message=exc.message,
        details=exc.details,
    )
    return _envelope(
        error_code=exc.error_code,
        message=exc.message,
        status_code=exc.status_code,
        details=exc.details or None,
    )


async def http_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    """Handle FastAPI/Starlette ``HTTPException`` (404, 405, abort, etc.)."""
    assert isinstance(exc, StarletteHTTPException)
    code_map = {
        status.HTTP_404_NOT_FOUND: "not_found",
        status.HTTP_405_METHOD_NOT_ALLOWED: "method_not_allowed",
        status.HTTP_401_UNAUTHORIZED: "unauthorized",
        status.HTTP_403_FORBIDDEN: "forbidden",
    }
    return _envelope(
        error_code=code_map.get(exc.status_code, "http_error"),
        message=str(exc.detail) if exc.detail else "HTTP error",
        status_code=exc.status_code,
    )


async def validation_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    """Handle Pydantic 422 — surfaces field-level errors in ``details``."""
    assert isinstance(exc, RequestValidationError)
    return _envelope(
        error_code="request_validation_error",
        message="Request validation failed.",
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        details={"errors": exc.errors()},
    )


async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    """Catch-all for unexpected exceptions. Never leaks internals to clients."""
    logger.exception("unhandled_exception", exc_type=type(exc).__name__)
    return _envelope(
        error_code="internal_error",
        message="Internal server error.",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach all handlers to the app. Called from ``main.py`` once at boot."""
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
