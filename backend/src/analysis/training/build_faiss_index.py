"""Build the FAISS store-similarity index from every store in the DB.

Usage::

    python -m src.analysis.training.build_faiss_index
    python -m src.analysis.training.build_faiss_index --version v2
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import date

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.analysis.scenario_c.feature_engineering import FeatureExtractor
from src.analysis.scenario_c.similarity_search import StoreSimilarityIndex
from src.analysis.training._mlflow_helpers import (
    mlflow_log_artifact,
    mlflow_log_metric,
    mlflow_log_param,
    mlflow_run,
)
from src.core.config import get_settings
from src.core.logging import app_logger, configure_logging
from src.models import Store

LOGGER = app_logger


async def _run_async(version: str) -> dict[str, object]:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, future=True)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    store_ids: list[int] = []
    vectors: list[np.ndarray] = []

    try:
        async with Session() as session:
            extractor = FeatureExtractor(session)
            result = await session.execute(
                select(Store.id, Store.opened_at).where(
                    Store.location.is_not(None),
                    Store.closed_at.is_(None),
                )
            )
            rows = list(result)
            for store_id, opened_at in rows:
                snap = opened_at or date.today()
                vec = await extractor.extract_for_store(int(store_id), snapshot_date=snap)
                if vec is None:
                    continue
                store_ids.append(int(store_id))
                vectors.append(vec.to_array().astype(np.float32))
    finally:
        await engine.dispose()

    if not vectors:
        raise RuntimeError(
            "No usable stores. Run `python -m src.scripts.seed --scenario c` first."
        )

    matrix = np.vstack(vectors).astype(np.float32)
    index = StoreSimilarityIndex.build(
        store_ids=store_ids, vectors=matrix, version=version
    )
    saved = index.save(settings.models_dir)

    with mlflow_run(experiment="faiss_store_index", run_name=f"build_{version}"):
        mlflow_log_param("version", version)
        mlflow_log_param("n_stores", len(store_ids))
        mlflow_log_param("dimension", index.dimension)
        mlflow_log_metric("n_stores", len(store_ids))
        mlflow_log_artifact(str(saved))

    LOGGER.info("faiss_index_built",
                version=version, n_stores=len(store_ids), path=str(saved))
    return {
        "version": version,
        "n_stores": len(store_ids),
        "dimension": index.dimension,
        "saved_path": str(saved),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build FAISS store similarity index")
    parser.add_argument("--version", default="v1")
    args = parser.parse_args()

    configure_logging()
    summary = asyncio.run(_run_async(args.version))
    print(f"[faiss] {summary}")  # noqa: T201


if __name__ == "__main__":
    main()
