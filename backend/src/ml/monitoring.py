"""ML inference monitoring helpers.

Stage 1 ships a tiny in-process counter + structured log emitter so route
handlers can wrap predictions without depending on a heavyweight stack.
Phase 2 replaces this with MLflow + Prometheus model-metrics exporters.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from src.core.logging import ml_logger


class InferenceMonitor:
    """Records latency + success/failure counts per ``(model, version)``."""

    def __init__(self) -> None:
        self._calls: dict[tuple[str, str], int] = {}
        self._errors: dict[tuple[str, str], int] = {}

    @asynccontextmanager
    async def measure(self, name: str, version: str = "v1") -> AsyncIterator[None]:
        """Context manager that times a prediction and logs the outcome.

        Usage::

            async with monitor.measure("suitability_dt", "v1"):
                score = model.predict(features)
        """
        key = (name, version)
        self._calls[key] = self._calls.get(key, 0) + 1
        started = time.perf_counter()
        try:
            yield
        except Exception:
            self._errors[key] = self._errors.get(key, 0) + 1
            ml_logger.exception("inference_error", model=name, version=version)
            raise
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1_000
            ml_logger.info(
                "inference_complete",
                model=name,
                version=version,
                duration_ms=round(elapsed_ms, 2),
            )

    def stats(self) -> dict[str, dict[str, int]]:
        """Return a snapshot of call/error counters."""
        out: dict[str, dict[str, int]] = {}
        for (name, version), calls in self._calls.items():
            out[f"{name}@{version}"] = {
                "calls": calls,
                "errors": self._errors.get((name, version), 0),
            }
        return out
