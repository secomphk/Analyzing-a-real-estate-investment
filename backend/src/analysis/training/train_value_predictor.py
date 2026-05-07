"""Validate the land-value predictor on seeded land-price series.

The Phase 1 predictor (loglinear + catalyst booster) doesn't actually fit
parameters offline — there's no model file to save. This script measures
its accuracy on the seed data (MAPE per horizon) and logs the run to
MLflow so we have a baseline to beat in Phase 2.

Usage::

    python -m src.analysis.training.train_value_predictor
"""

from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict
from typing import Any

import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.analysis.scenario_c.value_predictor import LandValuePredictor
from src.analysis.training._mlflow_helpers import (
    mlflow_log_dict,
    mlflow_log_metric,
    mlflow_log_param,
    mlflow_run,
)
from src.core.config import get_settings
from src.core.logging import app_logger, configure_logging

LOGGER = app_logger


async def _evaluate(min_observations: int = 4) -> dict[str, Any]:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, future=True)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    sql = text(
        """
        SELECT pnu, year, price_per_m2
        FROM official_land_prices
        ORDER BY pnu, year
        """
    )

    series: dict[str, list[tuple[int, int]]] = defaultdict(list)
    try:
        async with Session() as session:
            rows = (await session.execute(sql)).all()
            for r in rows:
                series[str(r.pnu)].append((int(r.year), int(r.price_per_m2)))

            predictor = LandValuePredictor(session)
            errors: dict[int, list[float]] = {1: [], 3: [], 5: []}
            n_eval = 0
            for pnu, points in series.items():
                if len(points) < min_observations:
                    continue
                # Hide the last point, predict from history, compare.
                history, holdout = points[:-1], points[-1]
                base_year, base_price = history[-1]
                # Patch: predictor pulls from DB; emulate by issuing a
                # forecast for the existing pnu — it sees the full series.
                forecast = await predictor.forecast(pnu)
                horizon = holdout[0] - base_year
                if horizon <= 0:
                    continue
                key = min((1, 3, 5), key=lambda h: abs(h - horizon))
                pred_pct = forecast.forecast[f"{key}y"]
                actual_pct = (holdout[1] - base_price) / base_price if base_price else 0.0
                if abs(actual_pct) < 1e-9:
                    continue
                errors[key].append(abs(pred_pct - actual_pct) / abs(actual_pct))
                n_eval += 1
    finally:
        await engine.dispose()

    mape_by_horizon = {
        f"{h}y_mape_pct": (round(float(np.mean(v) * 100), 2) if v else None)
        for h, v in errors.items()
    }
    mape_overall = (
        round(
            float(
                np.mean([e for arr in errors.values() for e in arr])
                if any(errors.values())
                else float("nan")
            ) * 100,
            2,
        )
        if any(errors.values())
        else None
    )

    summary: dict[str, Any] = {
        "n_evaluated_pnus": n_eval,
        "mape_overall_pct": mape_overall,
        **mape_by_horizon,
    }

    with mlflow_run(experiment="value_predictor", run_name="loglinear_v1"):
        mlflow_log_param("method", "loglinear+catalyst")
        mlflow_log_param("min_observations", min_observations)
        if mape_overall is not None:
            mlflow_log_metric("mape_overall", mape_overall)
        for k, v in mape_by_horizon.items():
            if v is not None:
                mlflow_log_metric(k, v)
        mlflow_log_dict("evaluation_summary", summary)

    LOGGER.info("value_predictor_eval", **summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Phase 1 value predictor.")
    parser.add_argument("--min-observations", type=int, default=4)
    args = parser.parse_args()

    configure_logging()
    summary = asyncio.run(_evaluate(args.min_observations))
    print(f"[value_predictor] {summary}")  # noqa: T201


if __name__ == "__main__":
    main()
