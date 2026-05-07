"""Stage-1 sanity check that model metadata loads without raising."""

from __future__ import annotations


def test_base_metadata_imports() -> None:
    from src.models.base import Base

    assert Base.metadata is not None
    # Stage 1 has no concrete tables yet — list will populate in Stage 2.
    assert isinstance(Base.metadata.tables, dict)
