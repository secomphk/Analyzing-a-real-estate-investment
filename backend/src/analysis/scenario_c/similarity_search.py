"""FAISS-backed store similarity index.

Cosine similarity ↔ L2-normalised vectors + ``IndexFlatIP``. The index is
small enough to live entirely in RAM for the Stage 1 dataset; sharding
to ``IndexIVFFlat`` will only be required once we exceed ~1M stores.

Index file layout::

    models_artifacts/
      faiss_index_v1.bin          # FAISS binary index
      faiss_index_v1.meta.json    # store_id ↔ row index mapping
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import faiss
import numpy as np
import numpy.typing as npt


@dataclass(slots=True, frozen=True)
class StoreSimilarityResult:
    """One similar-store result row."""

    store_id: int
    score: float                      # cosine similarity in [-1, 1]
    rank: int


@dataclass(slots=True)
class StoreSimilarityIndex:
    """In-memory FAISS index keyed by ``store_id``.

    Use :meth:`build` to create from raw vectors and :meth:`save` to
    persist. :meth:`load` rehydrates from disk.
    """

    dimension: int
    store_ids: list[int] = field(default_factory=list)
    index: faiss.IndexFlatIP | None = None
    version: str = "v1"

    # ─── Construction ───────────────────────────────────────────────────

    @classmethod
    def build(
        cls,
        *,
        store_ids: list[int],
        vectors: npt.NDArray[np.float32],
        version: str = "v1",
    ) -> StoreSimilarityIndex:
        """Build a fresh index. ``vectors`` is L2-normalised in place."""
        if vectors.shape[0] != len(store_ids):
            raise ValueError("store_ids and vectors length mismatch")
        if vectors.size == 0:
            raise ValueError("Cannot build a FAISS index over zero vectors")
        v = vectors.astype(np.float32, copy=True)
        faiss.normalize_L2(v)
        idx = faiss.IndexFlatIP(v.shape[1])
        idx.add(v)
        return cls(
            dimension=int(v.shape[1]),
            store_ids=list(store_ids),
            index=idx,
            version=version,
        )

    # ─── Search ─────────────────────────────────────────────────────────

    def search(
        self,
        query: npt.NDArray[np.float32],
        *,
        top_n: int = 5,
        exclude_store_id: int | None = None,
    ) -> list[StoreSimilarityResult]:
        if self.index is None:
            raise RuntimeError("Index not initialised — call build() or load() first.")
        q = query.astype(np.float32, copy=True).reshape(1, -1)
        if q.shape[1] != self.dimension:
            raise ValueError(
                f"Query dimension {q.shape[1]} != index dimension {self.dimension}"
            )
        faiss.normalize_L2(q)
        # Pull a few extra so we can filter the excluded store cleanly.
        k = min(top_n + 5, len(self.store_ids))
        scores, idxs = self.index.search(q, k)
        out: list[StoreSimilarityResult] = []
        for i, s in zip(idxs[0].tolist(), scores[0].tolist(), strict=True):
            if i == -1:
                continue
            sid = self.store_ids[i]
            if exclude_store_id is not None and sid == exclude_store_id:
                continue
            out.append(
                StoreSimilarityResult(
                    store_id=int(sid),
                    score=round(float(s), 4),
                    rank=len(out) + 1,
                )
            )
            if len(out) >= top_n:
                break
        return out

    # ─── Persistence ────────────────────────────────────────────────────

    def save(self, directory: Path | str) -> Path:
        if self.index is None:
            raise RuntimeError("Nothing to save — index is empty.")
        d = Path(directory)
        d.mkdir(parents=True, exist_ok=True)
        bin_path = d / f"faiss_index_{self.version}.bin"
        meta_path = d / f"faiss_index_{self.version}.meta.json"
        faiss.write_index(self.index, str(bin_path))
        meta_path.write_text(
            json.dumps(
                {
                    "version": self.version,
                    "dimension": self.dimension,
                    "store_ids": self.store_ids,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return bin_path

    @classmethod
    def load(
        cls,
        directory: Path | str,
        *,
        version: str = "v1",
    ) -> StoreSimilarityIndex:
        d = Path(directory)
        bin_path = d / f"faiss_index_{version}.bin"
        meta_path = d / f"faiss_index_{version}.meta.json"
        index = faiss.read_index(str(bin_path))
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return cls(
            dimension=int(meta["dimension"]),
            store_ids=list(meta["store_ids"]),
            index=index,
            version=meta.get("version", version),
        )
