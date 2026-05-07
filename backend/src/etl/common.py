"""Shared ETL utilities — error logging, dry-run helpers, kill switch.

Every ETL pipeline shares the same operational surface:

* ``--dry-run`` flag prevents any DB writes.
* Per-row failures are logged to ``data/errors/{date}.jsonl`` so a partial
  load doesn't lose visibility on what failed.
* A global env var ``ETL_KILL_SWITCH=1`` immediately raises so an operator
  can cut off all ingestion (e.g. when an upstream T&C changes).
* HTTP retries use ``tenacity`` with capped exponential backoff.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    RetryError,
    before_sleep_log,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.core.logging import app_logger

LOGGER = app_logger
"""Module logger reused by ETL pipelines for structured events."""

KILL_SWITCH_ENV = "ETL_KILL_SWITCH"
USER_AGENT_DEFAULT = "RealEstate-Analyzer/0.1 (+contact: hokeunpark.hp@gmail.com)"


class KillSwitchActivated(RuntimeError):
    """Raised when the operator-controlled kill switch is engaged."""


def check_kill_switch() -> None:
    """Raise :class:`KillSwitchActivated` if the kill switch env var is set.

    Called once at the start of every ETL command so a human can stop all
    ingestion without finding individual processes to kill.
    """
    if os.getenv(KILL_SWITCH_ENV, "").strip() in {"1", "true", "yes"}:
        raise KillSwitchActivated(
            f"{KILL_SWITCH_ENV} is set — refusing to run."
        )


def errors_log_path(base: str | Path = "data/errors") -> Path:
    """Resolve today's error-log path (one file per UTC date)."""
    today = date.today().isoformat()
    p = Path(base) / f"{today}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def log_row_error(
    *,
    pipeline: str,
    row: Mapping[str, Any],
    error: str,
    base: str | Path = "data/errors",
) -> None:
    """Append a single failed row + its error to the daily JSONL log.

    The row is preserved verbatim so the failure can be re-driven without
    going back to the upstream API.
    """
    payload = {
        "ts": datetime.now(tz=UTC).isoformat(),
        "pipeline": pipeline,
        "error": error,
        "row": dict(row),
    }
    with errors_log_path(base).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, default=str))
        fh.write("\n")


async def http_get_with_retry(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    attempts: int = 5,
) -> httpx.Response:
    """GET with capped exponential backoff (1s → 30s, ``attempts`` tries).

    Retries ``httpx.HTTPError`` (network + 5xx). 4xx errors are not retried —
    the caller should reshape the request instead.
    """
    import logging  # noqa: PLC0415 — local import keeps tenacity off structlog

    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(attempts),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        retry=retry_if_exception_type(httpx.HTTPError),
        before_sleep=before_sleep_log(logging.getLogger("etl.retry"), logging.WARNING),
        reraise=True,
    ):
        with attempt:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response
    # AsyncRetrying.reraise=True guarantees we never reach this; raise to
    # keep mypy happy and to fail loudly if tenacity ever changes behaviour.
    raise RetryError(last_attempt=None)  # type: ignore[arg-type]
