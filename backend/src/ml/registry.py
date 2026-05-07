"""In-process ML model registry.

Loads model artifacts from ``settings.models_dir`` at app startup and keeps
them on ``app.state.model_registry``. Routes get them via
``Depends(get_model("name", "v1"))`` (defined in ``api/deps.py``).

Filename convention::

    {name}_{version}.{ext}      # e.g. suitability_dt_v1.pkl
                                #      faiss_index_v1.bin

Supported extensions:

* ``.pkl`` / ``.joblib`` — joblib-loadable Python objects (sklearn, XGBoost
  via sklearn API, custom pipelines).
* ``.bin``               — FAISS index, loaded via ``faiss.read_index``.

Models can be pre-registered via ``preload`` (called from the FastAPI
lifespan) or fetched lazily with ``load_model``. Lookup is best-effort:
missing files do **not** crash the app — they only cause the corresponding
``Depends(get_model(...))`` to raise ``ModelNotLoadedError`` (503).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import joblib

from src.core.config import get_settings
from src.core.exceptions import ModelNotLoadedError
from src.core.logging import ml_logger


def _faiss_loader(path: Path) -> Any:
    """Lazy FAISS import — keeps faiss-cpu off the import path until needed."""
    import faiss  # noqa: PLC0415

    return faiss.read_index(str(path))


_LOADERS: dict[str, Any] = {
    ".pkl": joblib.load,
    ".joblib": joblib.load,
    ".bin": _faiss_loader,
}


@dataclass
class _Entry:
    """One cached model + the path it was loaded from."""

    model: Any
    path: Path


@dataclass
class ModelRegistry:
    """Process-wide lookup keyed by ``(name, version)``.

    Construct one and stash it on ``app.state``. ``preload`` is the typical
    entry point during lifespan startup; routes use ``get`` (returns None
    on miss) or ``require`` (raises ``ModelNotLoadedError``).
    """

    models_dir: Path
    _cache: dict[tuple[str, str], _Entry] = field(default_factory=dict)

    # ─── Public API ─────────────────────────────────────────────────────

    def load_model(self, name: str, version: str = "v1") -> Any:
        """Load a model from disk and cache it. Idempotent.

        Args:
            name: Logical model name (e.g. ``"suitability_dt"``).
            version: Version tag — must match the filename suffix
                (``..._v1.pkl``). Defaults to ``"v1"``.

        Returns:
            The deserialized model object.

        Raises:
            ModelNotLoadedError: No matching artifact found in
                ``models_dir`` (any supported extension).
        """
        key = (name, version)
        if key in self._cache:
            return self._cache[key].model

        path = self._resolve_path(name, version)
        if path is None:
            ml_logger.warning(
                "model_artifact_missing",
                name=name,
                version=version,
                models_dir=str(self.models_dir),
            )
            raise ModelNotLoadedError(
                f"No artifact for {name}@{version} in {self.models_dir}"
            )

        loader = _LOADERS[path.suffix]
        ml_logger.info("model_loading", name=name, version=version, path=str(path))
        model = loader(path)
        self._cache[key] = _Entry(model=model, path=path)
        ml_logger.info("model_loaded", name=name, version=version, path=str(path))
        return model

    def get(self, name: str, version: str = "v1") -> Any | None:
        """Return a cached model or ``None`` (no disk access, no exception)."""
        entry = self._cache.get((name, version))
        return entry.model if entry else None

    def require(self, name: str, version: str = "v1") -> Any:
        """Like ``get`` but raises ``ModelNotLoadedError`` on miss."""
        model = self.get(name, version)
        if model is None:
            raise ModelNotLoadedError(f"Model not loaded: {name}@{version}")
        return model

    def preload(self, names: list[tuple[str, str]]) -> None:
        """Try to load every ``(name, version)`` pair. Misses are logged, not raised.

        Use from the FastAPI lifespan so the API stays up even if some
        artifacts haven't been published yet.
        """
        for name, version in names:
            try:
                self.load_model(name, version)
            except ModelNotLoadedError:
                # Already logged inside load_model.
                continue

    def unload_all(self) -> None:
        """Drop all references. Lifespan shutdown should call this."""
        self._cache.clear()

    def list_loaded(self) -> list[dict[str, str]]:
        """Introspection helper for /health-style readiness reporting."""
        return [
            {"name": name, "version": version, "path": str(entry.path)}
            for (name, version), entry in self._cache.items()
        ]

    # ─── MLflow integration (optional) ──────────────────────────────────
    # The MVP runs entirely off local artifacts. When MLflow is reachable
    # (production), the methods below resolve the "Production" stage of a
    # registered model so we can promote / roll back without redeploying.

    def load_production(self, name: str) -> Any:
        """Pull the current Production version of ``name`` from MLflow.

        Falls back to local ``load_model(name, 'v1')`` when MLflow isn't
        reachable so dev environments stay self-sufficient.
        """
        try:
            import mlflow  # noqa: PLC0415
            from mlflow.tracking import MlflowClient  # noqa: PLC0415
        except Exception as exc:  # noqa: BLE001
            ml_logger.warning("mlflow_unavailable", error=str(exc))
            return self.load_model(name, "v1")

        try:
            mlflow.set_tracking_uri(get_settings().mlflow_tracking_uri)
            client = MlflowClient()
            versions = client.get_latest_versions(name, stages=["Production"])
            if not versions:
                ml_logger.warning("mlflow_no_production_version", name=name)
                return self.load_model(name, "v1")
            v = versions[0]
            uri = f"models:/{name}/{v.version}"
            ml_logger.info("mlflow_loading", name=name, version=v.version, uri=uri)
            model = mlflow.pyfunc.load_model(uri)
            self._cache[(name, f"prod_{v.version}")] = _Entry(
                model=model, path=Path(uri)
            )
            return model
        except Exception as exc:  # noqa: BLE001
            ml_logger.error("mlflow_load_failed", name=name, error=str(exc))
            return self.load_model(name, "v1")

    def promote_to_production(self, name: str, version: str | int) -> None:
        """Move ``(name, version)`` from Staging → Production in MLflow.

        Archives any prior Production versions so there's exactly one.
        No-op + warning when MLflow isn't configured.
        """
        try:
            import mlflow  # noqa: PLC0415
            from mlflow.tracking import MlflowClient  # noqa: PLC0415
        except Exception as exc:  # noqa: BLE001
            ml_logger.warning(
                "mlflow_unavailable_for_promotion", name=name, error=str(exc)
            )
            return

        mlflow.set_tracking_uri(get_settings().mlflow_tracking_uri)
        client = MlflowClient()
        client.transition_model_version_stage(
            name=name,
            version=str(version),
            stage="Production",
            archive_existing_versions=True,
        )
        ml_logger.info("model_promoted", name=name, version=str(version))

    def rollback(self, name: str) -> str | None:
        """Promote the most recent Archived version of ``name`` back to Production.

        Returns the version that was promoted, or ``None`` if nothing was
        eligible. Used by the on-call runbook when a fresh model regresses.
        """
        try:
            import mlflow  # noqa: PLC0415
            from mlflow.tracking import MlflowClient  # noqa: PLC0415
        except Exception as exc:  # noqa: BLE001
            ml_logger.warning("mlflow_unavailable_for_rollback", error=str(exc))
            return None

        mlflow.set_tracking_uri(get_settings().mlflow_tracking_uri)
        client = MlflowClient()
        archived = client.get_latest_versions(name, stages=["Archived"])
        if not archived:
            ml_logger.warning("rollback_no_archived_version", name=name)
            return None
        # Most-recent archived version (largest version number).
        target = max(archived, key=lambda v: int(v.version))
        client.transition_model_version_stage(
            name=name,
            version=target.version,
            stage="Production",
            archive_existing_versions=True,
        )
        ml_logger.warning("model_rolled_back", name=name, version=target.version)
        return str(target.version)

    # ─── Internal ───────────────────────────────────────────────────────

    def _resolve_path(self, name: str, version: str) -> Path | None:
        """Find ``{name}_{version}.{ext}`` for any supported extension."""
        for ext in _LOADERS:
            candidate = self.models_dir / f"{name}_{version}{ext}"
            if candidate.exists():
                return candidate
        return None


def build_registry() -> ModelRegistry:
    """Construct the registry using settings. Called from main.py lifespan."""
    settings = get_settings()
    settings.models_dir.mkdir(parents=True, exist_ok=True)
    return ModelRegistry(models_dir=settings.models_dir)
