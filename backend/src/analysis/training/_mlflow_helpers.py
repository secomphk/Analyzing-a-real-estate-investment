"""Tiny wrappers around MLflow so training scripts stay quiet when the
tracking server is unreachable.

Use as::

    with mlflow_run("suitability_dt") as run:
        mlflow_log_metric("auc", auc_score)

If MLflow is offline, the calls become no-ops + a warning log line.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from src.core.config import get_settings
from src.core.logging import ml_logger


@contextmanager
def mlflow_run(experiment: str, *, run_name: str | None = None) -> Iterator[Any]:
    """Yield an active MLflow run, or a stub when MLflow is unavailable."""
    try:
        import mlflow  # noqa: PLC0415

        settings = get_settings()
        mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
        mlflow.set_experiment(experiment)
        with mlflow.start_run(run_name=run_name) as run:
            yield run
    except Exception as exc:
        ml_logger.warning("mlflow_unavailable", experiment=experiment, error=str(exc))

        class _Noop:
            info = type("RunInfo", (), {"run_id": "noop"})

        yield _Noop()


def mlflow_log_metric(key: str, value: float) -> None:
    try:
        import mlflow  # noqa: PLC0415

        mlflow.log_metric(key, float(value))
    except Exception:
        pass


def mlflow_log_param(key: str, value: Any) -> None:
    try:
        import mlflow  # noqa: PLC0415

        mlflow.log_param(key, value)
    except Exception:
        pass


def mlflow_log_dict(key: str, value: dict[str, Any]) -> None:
    try:
        import mlflow  # noqa: PLC0415

        mlflow.log_dict(value, f"{key}.json")
    except Exception:
        pass


def mlflow_log_artifact(path: str) -> None:
    try:
        import mlflow  # noqa: PLC0415

        mlflow.log_artifact(path)
    except Exception:
        pass
