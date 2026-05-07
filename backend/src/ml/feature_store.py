"""Redis-backed feature store with a 24h default TTL.

Key format::

    feature:{entity_type}:{id}:{snapshot_date}

* ``entity_type`` — ``store``, ``region``, ``project``, ``road``.
* ``id``          — primary key in the source table.
* ``snapshot_date`` — ``YYYY-MM-DD`` (UTC); use ``"latest"`` for live values.

Values are JSON-encoded dicts of feature_name → numeric/categorical values.
Stage 1 ships only the read/write surface; the ETL writers and online
inference paths land in Stage 2/3.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any, Final

from src.core.config import get_settings
from src.core.logging import ml_logger

KEY_PREFIX: Final[str] = "feature"


def _key(entity_type: str, entity_id: str | int, snapshot: str | date | None) -> str:
    """Build the canonical Redis key for a feature row."""
    snap = (
        snapshot.isoformat()
        if isinstance(snapshot, date)
        else (snapshot or "latest")
    )
    return f"{KEY_PREFIX}:{entity_type}:{entity_id}:{snap}"


class FeatureStore:
    """Thin async wrapper around Redis for feature caching."""

    def __init__(self, redis: Any, ttl_seconds: int | None = None) -> None:
        self._redis = redis
        self._ttl = ttl_seconds or get_settings().feature_cache_ttl_seconds

    async def get(
        self,
        entity_type: str,
        entity_id: str | int,
        snapshot: str | date | None = None,
    ) -> dict[str, Any] | None:
        """Return the cached feature row, or ``None`` on miss."""
        raw = await self._redis.get(_key(entity_type, entity_id, snapshot))
        if raw is None:
            return None
        try:
            value: dict[str, Any] = (
                json.loads(raw) if isinstance(raw, str) else json.loads(raw.decode())
            )
            return value
        except json.JSONDecodeError:
            ml_logger.warning(
                "feature_cache_decode_error",
                entity_type=entity_type,
                entity_id=entity_id,
            )
            return None

    async def set(
        self,
        entity_type: str,
        entity_id: str | int,
        features: dict[str, Any],
        snapshot: str | date | None = None,
        *,
        ttl_seconds: int | None = None,
    ) -> None:
        """Store a feature row with the configured TTL."""
        await self._redis.set(
            _key(entity_type, entity_id, snapshot),
            json.dumps(features, default=str),
            ex=ttl_seconds or self._ttl,
        )

    async def delete(
        self,
        entity_type: str,
        entity_id: str | int,
        snapshot: str | date | None = None,
    ) -> int:
        """Drop a single feature row. Returns 1 if it existed, else 0."""
        return int(await self._redis.delete(_key(entity_type, entity_id, snapshot)))

    async def get_many(
        self,
        entity_type: str,
        entity_ids: list[str | int],
        snapshot: str | date | None = None,
    ) -> dict[str | int, dict[str, Any] | None]:
        """Pipelined multi-get keyed by entity_id."""
        keys = [_key(entity_type, eid, snapshot) for eid in entity_ids]
        raw_values = await self._redis.mget(keys)
        out: dict[str | int, dict[str, Any] | None] = {}
        for eid, raw in zip(entity_ids, raw_values, strict=True):
            if raw is None:
                out[eid] = None
                continue
            try:
                out[eid] = (
                    json.loads(raw) if isinstance(raw, str) else json.loads(raw.decode())
                )
            except json.JSONDecodeError:
                out[eid] = None
        return out
