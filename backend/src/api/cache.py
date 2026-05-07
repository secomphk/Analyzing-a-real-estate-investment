"""Redis-backed analysis-result cache.

Computes a stable ``input_hash`` for the request payload and looks up a
cached result keyed by ``(scenario, entity_type, entity_id, hash)``. On a
miss, the route runs the analysis, writes the result back, and (best-effort)
persists the run to ``analysis_results``.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import app_logger
from src.core.metrics import record_cache
from src.core.redis_client import get_redis

LOGGER = app_logger
DEFAULT_TTL_SECONDS = 3_600


def make_input_hash(payload: dict[str, Any]) -> str:
    """Stable SHA1 over ``json.dumps(payload, sort_keys=True)``."""
    blob = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:32]


def make_redis_key(
    *, scenario: str, entity_type: str, entity_id: str, params_hash: str
) -> str:
    return f"analysis:{scenario}:{entity_type}:{entity_id}:{params_hash}"


async def cached_compute(
    *,
    session: AsyncSession,
    scenario: str,
    entity_type: str,
    entity_id: str,
    payload: dict[str, Any],
    compute: Callable[[], Awaitable[dict[str, Any]]],
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    persist: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Look up Redis → return cached result; miss → run ``compute`` and store.

    Returns ``(result, meta_info)`` where ``meta_info`` carries
    ``cache_hit`` / ``computation_time_ms`` for the response envelope.
    """
    params_hash = make_input_hash(payload)
    key = make_redis_key(
        scenario=scenario,
        entity_type=entity_type,
        entity_id=entity_id,
        params_hash=params_hash,
    )

    redis = get_redis()
    started = time.perf_counter()
    try:
        cached = await redis.get(key)
    except Exception as exc:  # noqa: BLE001 — never block on Redis
        LOGGER.warning("cache_get_failed", key=key, error=str(exc))
        cached = None

    if cached:
        result = json.loads(cached) if isinstance(cached, str) else json.loads(cached.decode())
        elapsed = (time.perf_counter() - started) * 1_000
        record_cache(scenario, hit=True)
        return result, {"cache_hit": True, "computation_time_ms": round(elapsed, 2)}

    # Cache miss — actually run the analysis.
    record_cache(scenario, hit=False)
    result = await compute()
    elapsed = (time.perf_counter() - started) * 1_000

    try:
        await redis.set(key, json.dumps(result, default=str), ex=ttl_seconds)
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("cache_set_failed", key=key, error=str(exc))

    if persist:
        try:
            await _persist_run(
                session=session,
                scenario=scenario,
                entity_type=entity_type,
                entity_id=entity_id,
                params_hash=params_hash,
                payload=payload,
                result=result,
            )
        except Exception as exc:  # noqa: BLE001 — DB failures shouldn't kill the response
            LOGGER.warning("analysis_persist_failed", error=str(exc), scenario=scenario)

    return result, {"cache_hit": False, "computation_time_ms": round(elapsed, 2)}


async def _persist_run(
    *,
    session: AsyncSession,
    scenario: str,
    entity_type: str,
    entity_id: str,
    params_hash: str,
    payload: dict[str, Any],
    result: dict[str, Any],
) -> None:
    """Best-effort UPSERT into ``analysis_results``."""
    sql = text(
        """
        INSERT INTO analysis_results (
            scenario, entity_type, entity_id, params_hash,
            status, finished_at, params, result
        )
        VALUES (
            :scenario, :entity_type, :entity_id, :params_hash,
            'completed', NOW(),
            CAST(:params AS jsonb),
            CAST(:result AS jsonb)
        )
        ON CONFLICT ON CONSTRAINT uq_analysis_results_scenario_entity_params
        DO UPDATE SET
            result      = EXCLUDED.result,
            status      = 'completed',
            finished_at = NOW()
        """
    ).bindparams(
        bindparam("scenario", value=scenario),
        bindparam("entity_type", value=entity_type),
        bindparam("entity_id", value=entity_id),
        bindparam("params_hash", value=params_hash),
        bindparam("params", value=json.dumps(payload, default=str)),
        bindparam("result", value=json.dumps(result, default=str)),
    )
    async with session.begin_nested():
        await session.execute(sql)
        await session.commit()
