"""Stage-1 sanity check: ModelRegistry behaves on missing/loadable artifacts."""

from __future__ import annotations

from pathlib import Path

import joblib
import pytest

from src.core.exceptions import ModelNotLoadedError
from src.ml.registry import ModelRegistry


def test_registry_misses_raise(tmp_path: Path) -> None:
    registry = ModelRegistry(models_dir=tmp_path)
    with pytest.raises(ModelNotLoadedError):
        registry.load_model("nope", "v1")
    assert registry.get("nope", "v1") is None


def test_registry_loads_and_caches_pkl(tmp_path: Path) -> None:
    artifact = {"hello": "world"}
    joblib.dump(artifact, tmp_path / "fake_model_v1.pkl")

    registry = ModelRegistry(models_dir=tmp_path)
    loaded = registry.load_model("fake_model", "v1")
    assert loaded == artifact

    # Cache hit on second call — no disk access expected.
    assert registry.get("fake_model", "v1") is loaded
    assert any(m["name"] == "fake_model" for m in registry.list_loaded())

    registry.unload_all()
    assert registry.list_loaded() == []
