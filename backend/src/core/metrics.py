"""Custom Prometheus metrics layered on top of prometheus-fastapi-instrumentator.

The instrumentator already covers HTTP-level latency / status histograms;
this module adds the business + ML metrics that the Stage 5 dashboard needs:

* ``model_predictions_total{model,version,target}`` — counter
* ``model_prediction_duration_seconds{model,version}`` — histogram
* ``cache_hits_total{scenario}`` / ``cache_misses_total{scenario}``
* ``etl_records_processed_total{pipeline,outcome}``

Counters / histograms are module-level singletons so the values survive
across requests. The :class:`MeasurePrediction` context manager is the
ergonomic wrapper used from analysis routes / training scripts.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from prometheus_client import Counter, Histogram

# ─── Metric definitions ─────────────────────────────────────────────────────

PREDICTION_COUNTER = Counter(
    "model_predictions_total",
    "Number of model predictions served, by model + version + target.",
    labelnames=("model", "version", "target", "outcome"),
)

PREDICTION_LATENCY = Histogram(
    "model_prediction_duration_seconds",
    "Wall-clock latency of one prediction.",
    labelnames=("model", "version"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

CACHE_HITS = Counter(
    "cache_hits_total",
    "Analysis cache hits, by scenario tag.",
    labelnames=("scenario",),
)

CACHE_MISSES = Counter(
    "cache_misses_total",
    "Analysis cache misses, by scenario tag.",
    labelnames=("scenario",),
)

ETL_RECORDS = Counter(
    "etl_records_processed_total",
    "ETL records processed, by pipeline + outcome (accepted / rejected).",
    labelnames=("pipeline", "outcome"),
)


# ─── Convenience wrappers ───────────────────────────────────────────────────


@asynccontextmanager
async def measure_prediction(
    *,
    model: str,
    version: str = "v1",
    target: str = "default",
) -> AsyncIterator[None]:
    """Time a prediction + bump the counters.

    Usage::

        async with measure_prediction(model="suitability_dt", target="DT"):
            score = model.predict(features)

    Failed predictions still record latency but the counter records
    ``outcome="error"`` so dashboards can break out the failure rate.
    """
    started = time.perf_counter()
    try:
        yield
    except Exception:
        PREDICTION_COUNTER.labels(model, version, target, "error").inc()
        raise
    else:
        PREDICTION_COUNTER.labels(model, version, target, "ok").inc()
    finally:
        PREDICTION_LATENCY.labels(model, version).observe(
            time.perf_counter() - started
        )


def record_cache(scenario: str, *, hit: bool) -> None:
    """Bump cache-hit / cache-miss counters from the request handlers."""
    if hit:
        CACHE_HITS.labels(scenario).inc()
    else:
        CACHE_MISSES.labels(scenario).inc()


def record_etl(pipeline: str, *, accepted: int = 0, rejected: int = 0) -> None:
    """Bump ETL counters in a single call (matches the ETL return shape)."""
    if accepted:
        ETL_RECORDS.labels(pipeline, "accepted").inc(accepted)
    if rejected:
        ETL_RECORDS.labels(pipeline, "rejected").inc(rejected)
