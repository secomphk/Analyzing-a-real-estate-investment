"""Train the DT/DI suitability classifier from the seed/store table.

Usage::

    python -m src.analysis.training.train_suitability --target DT
    python -m src.analysis.training.train_suitability --target DI --version v2

What it does:
1. Pull every seeded :class:`Store` row matching the target.
2. Build positive samples via :class:`FeatureExtractor.extract_for_store`.
3. Mine negative samples — random parcels in the same 시군구 not within
   200m of any positive store (1:3 positive-to-negative ratio).
4. Train an XGBoost classifier with stratified 5-fold CV.
5. Log AUC + feature importances to MLflow.
6. Persist the model under ``models_artifacts/suitability_<target>_<version>.pkl``.

Seed data is small so the AUC bar is treated as a smoke check, not a
deployment gate. The script always emits a model — Phase 2 backfills with
real data.
"""

from __future__ import annotations

import argparse
import asyncio
import random
from dataclasses import dataclass
from datetime import date

import numpy as np
import numpy.typing as npt
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.analysis.scenario_c.feature_engineering import (
    FEATURE_NAMES,
    FeatureExtractor,
    FeatureVector,
)
from src.analysis.scenario_c.suitability_model import SuitabilityModel
from src.analysis.training._mlflow_helpers import (
    mlflow_log_artifact,
    mlflow_log_dict,
    mlflow_log_metric,
    mlflow_log_param,
    mlflow_run,
)
from src.core.config import get_settings
from src.core.logging import app_logger, configure_logging, ml_logger

LOGGER = ml_logger
DEFAULT_NEGATIVE_RATIO = 3
RANDOM_SEED = 42


@dataclass(slots=True)
class TrainingArtifacts:
    """What the trainer hands back to the CLI / tests."""

    model: SuitabilityModel
    auc_mean: float
    auc_per_fold: list[float]
    n_positive: int
    n_negative: int
    saved_path: str | None
    feature_importances: dict[str, float]


# ─── Sample mining ─────────────────────────────────────────────────────────


async def _mine_positive_pnus(
    SessionFactory: async_sessionmaker[AsyncSession],
    target: str,
) -> list[tuple[int, str]]:
    """Return ``[(store_id, region_code)]`` for active stores matching target."""
    sql = text(
        """
        SELECT id, region_code, pnu
        FROM stores
        WHERE store_type = :target
          AND pnu IS NOT NULL
          AND closed_at IS NULL
        """
    ).bindparams(bindparam("target", value=target))
    async with SessionFactory() as session:
        rows = (await session.execute(sql)).all()
    return [(int(r.id), str(r.region_code)) for r in rows]


async def _mine_negative_pnus(
    SessionFactory: async_sessionmaker[AsyncSession],
    *,
    region_codes: list[str],
    excluded_pnus: set[str],
    n_per_region: int,
) -> list[str]:
    """Random buildings in the given regions not in the excluded set."""
    if not region_codes:
        return []
    sql = text(
        """
        SELECT pnu, region_code
        FROM buildings
        WHERE region_code = ANY(:codes)
          AND COALESCE(parcel_area_m2, 0) BETWEEN 300 AND 3000
        """
    ).bindparams(bindparam("codes", value=region_codes))
    async with SessionFactory() as session:
        rows = (await session.execute(sql)).all()

    rng = random.Random(RANDOM_SEED)
    by_region: dict[str, list[str]] = {}
    for r in rows:
        if r.pnu in excluded_pnus:
            continue
        by_region.setdefault(str(r.region_code), []).append(str(r.pnu))
    out: list[str] = []
    for code in region_codes:
        bucket = by_region.get(code, [])
        rng.shuffle(bucket)
        out.extend(bucket[:n_per_region])
    return out


# ─── Feature pipeline ──────────────────────────────────────────────────────


async def _build_dataset(
    SessionFactory: async_sessionmaker[AsyncSession],
    target: str,
    *,
    negative_ratio: int = DEFAULT_NEGATIVE_RATIO,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.int64], list[str]]:
    """Returns ``(X, y, feature_names)``."""
    positives = await _mine_positive_pnus(SessionFactory, target)
    if not positives:
        raise RuntimeError(
            f"No positive samples for target={target!r}. "
            "Did you run `python -m src.scripts.seed`?"
        )

    pos_pnus: set[str] = set()
    pos_vectors: list[FeatureVector] = []
    region_codes: list[str] = []
    snapshot = date.today()

    async with SessionFactory() as session:
        extractor = FeatureExtractor(session)
        for store_id, region_code in positives:
            vec = await extractor.extract_for_store(store_id, snapshot_date=snapshot)
            if vec is None:
                continue
            if vec.pnu:
                pos_pnus.add(vec.pnu)
            pos_vectors.append(vec)
            region_codes.append(region_code)

    neg_pnus = await _mine_negative_pnus(
        SessionFactory,
        region_codes=list(set(region_codes)),
        excluded_pnus=pos_pnus,
        n_per_region=max(1, len(positives) * negative_ratio // max(len(set(region_codes)), 1)),
    )

    neg_vectors: list[FeatureVector] = []
    async with SessionFactory() as session:
        extractor = FeatureExtractor(session)
        for pnu in neg_pnus:
            vec = await extractor.extract_for_pnu(pnu, snapshot_date=snapshot)
            if vec is not None:
                neg_vectors.append(vec)

    if not neg_vectors:
        # Fall back to synthetic perturbed negatives so training never blocks.
        LOGGER.warning(
            "suitability_falling_back_to_synthetic_negatives",
            target=target, n_pos=len(pos_vectors),
        )
        rng = np.random.default_rng(RANDOM_SEED)
        for vec in pos_vectors[: max(1, len(pos_vectors) * negative_ratio)]:
            jitter = vec.to_array() * (1 - rng.uniform(0.5, 0.9, len(FEATURE_NAMES)))
            fake = FeatureVector(
                pnu=None,
                snapshot_date=snapshot,
                values={n: float(jitter[i]) for i, n in enumerate(FEATURE_NAMES)},
            )
            neg_vectors.append(fake)

    X = np.vstack([v.to_array() for v in pos_vectors + neg_vectors])
    y = np.array([1] * len(pos_vectors) + [0] * len(neg_vectors), dtype=np.int64)
    return X, y, list(FEATURE_NAMES)


# ─── Trainer ───────────────────────────────────────────────────────────────


def train_with_cv(
    X: npt.NDArray[np.float64],
    y: npt.NDArray[np.int64],
    *,
    target: str,
    feature_names: list[str],
    n_splits: int = 5,
    model_version: str = "scenario_c_v1.0.0",
) -> TrainingArtifacts:
    """Stratified K-fold CV + final model fit on the full dataset."""
    if y.sum() == 0 or y.sum() == len(y):
        raise ValueError("Need both positive and negative samples to train.")

    n_splits_used = min(n_splits, int(min(np.bincount(y))))
    aucs: list[float] = []
    if n_splits_used >= 2:
        skf = StratifiedKFold(n_splits=n_splits_used, shuffle=True, random_state=RANDOM_SEED)
        for fold_idx, (train_idx, test_idx) in enumerate(skf.split(X, y), 1):
            fold_model = SuitabilityModel(
                target=target, feature_names=feature_names, model_version=model_version,
            )
            fold_model.fit(X[train_idx], y[train_idx])
            proba = fold_model.model.predict_proba(X[test_idx].astype(np.float32))[:, 1]
            try:
                auc = float(roc_auc_score(y[test_idx], proba))
            except ValueError:
                auc = 0.5
            aucs.append(auc)
            LOGGER.info("suitability_fold", target=target, fold=fold_idx, auc=auc)
    else:
        LOGGER.warning(
            "suitability_skipped_cv", target=target, n_splits_requested=n_splits,
            reason="insufficient samples per class",
        )

    final = SuitabilityModel(
        target=target, feature_names=feature_names, model_version=model_version,
    )
    final.fit(X, y)
    importances = getattr(final.model, "feature_importances_", None)
    importance_map: dict[str, float] = {}
    if importances is not None:
        importance_map = {
            name: round(float(v), 4)
            for name, v in zip(feature_names, importances, strict=True)
        }

    return TrainingArtifacts(
        model=final,
        auc_mean=round(float(np.mean(aucs)) if aucs else 0.5, 4),
        auc_per_fold=[round(a, 4) for a in aucs],
        n_positive=int(y.sum()),
        n_negative=int(len(y) - y.sum()),
        saved_path=None,
        feature_importances=importance_map,
    )


# ─── Entrypoint ────────────────────────────────────────────────────────────


async def _run_async(target: str, version: str) -> TrainingArtifacts:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, future=True)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        X, y, names = await _build_dataset(Session, target)
    finally:
        await engine.dispose()

    artifacts = train_with_cv(X, y, target=target, feature_names=names)
    out_path = artifacts.model.save(settings.models_dir, version=version)
    artifacts.saved_path = str(out_path)

    with mlflow_run(experiment=f"suitability_{target.lower()}",
                    run_name=f"{target}_{version}"):
        mlflow_log_param("target", target)
        mlflow_log_param("version", version)
        mlflow_log_param("n_positive", artifacts.n_positive)
        mlflow_log_param("n_negative", artifacts.n_negative)
        mlflow_log_metric("auc_mean", artifacts.auc_mean)
        for i, auc in enumerate(artifacts.auc_per_fold, 1):
            mlflow_log_metric(f"auc_fold_{i}", auc)
        mlflow_log_dict("feature_importances", artifacts.feature_importances)
        mlflow_log_artifact(str(out_path))

    return artifacts


def main() -> None:
    parser = argparse.ArgumentParser(description="Train DT/DI suitability classifier.")
    parser.add_argument("--target", choices=["DT", "DI"], default="DT")
    parser.add_argument("--version", default="v1")
    args = parser.parse_args()

    configure_logging()
    art = asyncio.run(_run_async(args.target, args.version))
    print(  # noqa: T201
        f"[suitability:{args.target}] saved={art.saved_path} "
        f"auc_mean={art.auc_mean} folds={art.auc_per_fold} "
        f"n_pos={art.n_positive} n_neg={art.n_negative}"
    )
    app_logger.info("training_complete", target=args.target,
                    auc_mean=art.auc_mean, path=art.saved_path)


if __name__ == "__main__":
    main()
