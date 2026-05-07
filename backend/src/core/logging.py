"""Structured logging with structlog.

JSON in production / non-dev; coloured key=value renderer in development for
readability. A request-scoped contextvar carries ``request_id`` so every log
line emitted while handling one request shares an id (set by middleware).

Two named loggers are exposed for convenience:

* ``app_logger``  — general application logs.
* ``ml_logger``   — model load/predict events (separate so ML telemetry can
  be routed independently in prod).
"""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from typing import Any

import structlog
from structlog.contextvars import merge_contextvars
from structlog.types import EventDict, Processor

from src.core.config import Environment, get_settings

# Request-scoped id; middleware writes it before the route runs.
request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)


def _add_request_id(_: object, __: str, event_dict: EventDict) -> EventDict:
    """Inject the contextvar's request_id into every log record."""
    rid = request_id_ctx.get()
    if rid is not None:
        event_dict.setdefault("request_id", rid)
    return event_dict


# Field names whose values must never appear in plain text in logs.
# We normalise both the key name and these substrings to lowercase
# letters-only so ``AccessKey``, ``access_key``, ``access-key`` and
# ``ACCESSKEY`` all match.
_SENSITIVE_KEY_SUBSTRINGS: tuple[str, ...] = (
    "password",
    "passwd",
    "secret",
    "token",
    "authorization",
    "apikey",
    "accesskey",
    "credential",
    "cookie",
)
_REDACTED = "***redacted***"


def _normalize_key(key: str) -> str:
    """Lowercase + strip non-alphanumerics — matches snake/camel/kebab casing."""
    return "".join(ch for ch in key.lower() if ch.isalnum())


def _is_sensitive(key: str) -> bool:
    normalized = _normalize_key(key)
    return any(s in normalized for s in _SENSITIVE_KEY_SUBSTRINGS)


def _sanitize(_: object, __: str, event_dict: EventDict) -> EventDict:
    """Redact sensitive keys before they leave the process.

    Walks the event dict (depth 1 — nested dicts get their direct keys
    redacted but we don't recurse into Mapping values that aren't dicts,
    which keeps the cost predictable).
    """
    for key in list(event_dict.keys()):
        if _is_sensitive(key):
            event_dict[key] = _REDACTED
            continue
        value = event_dict[key]
        if isinstance(value, dict):
            for inner in list(value.keys()):
                if _is_sensitive(inner):
                    value[inner] = _REDACTED
    return event_dict


def configure_logging() -> None:
    """Wire up structlog + stdlib logging once at app start.

    Idempotent: safe to call from both ``main.py`` and tests.
    """
    settings = get_settings()
    level = getattr(logging, settings.log_level.value)

    shared_processors: list[Processor] = [
        merge_contextvars,
        _add_request_id,
        _sanitize,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.environment == Environment.DEVELOPMENT:
        renderer: Processor = structlog.dev.ConsoleRenderer(colors=True)
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Route stdlib logs (uvicorn, sqlalchemy, etc.) through the same pipeline.
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    # Quiet noisy libraries.
    for noisy in ("uvicorn.access", "watchfiles", "asyncio"):
        logging.getLogger(noisy).setLevel(max(level, logging.WARNING))


def get_logger(name: str = "app") -> Any:
    """Return a bound structlog logger.

    Args:
        name: Logger name shown in the ``logger`` field. Use ``"ml"`` for
            ML-specific events to make them filterable downstream.

    Returns:
        A structlog ``BoundLogger`` ready for ``.info(...)``, ``.error(...)``.
    """
    return structlog.get_logger(name)


# Convenience handles for callers that don't need a custom name.
app_logger = get_logger("app")
ml_logger = get_logger("ml")
