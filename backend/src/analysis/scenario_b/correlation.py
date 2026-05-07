"""Pairwise Pearson correlation across the 3 Scenario B variables.

Pure NumPy — no DB. The downstream :class:`ThreeVariableAnalyzer` feeds in
already-aligned series (one row per month).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np


@dataclass(slots=True)
class CorrelationMatrix:
    """Symmetric correlation matrix indexed by variable name."""

    variables: list[str]
    matrix: list[list[float]]

    def get(self, a: str, b: str) -> float:
        """Return ``corr(a, b)``. Raises ``KeyError`` for unknown names."""
        i = self.variables.index(a)
        j = self.variables.index(b)
        return self.matrix[i][j]


def pearson_matrix(series: Mapping[str, list[float]]) -> CorrelationMatrix:
    """Compute Pearson correlation between every pair of equal-length series."""
    if not series:
        return CorrelationMatrix(variables=[], matrix=[])

    names = list(series.keys())
    arrays = [np.asarray(series[n], dtype=np.float64) for n in names]
    length = arrays[0].size
    if not all(a.size == length for a in arrays):
        raise ValueError("All series must have identical length.")

    if length < 3:
        # Correlation undefined; return a zero matrix with the right shape.
        zero = [[0.0] * len(names) for _ in names]
        for i in range(len(names)):
            zero[i][i] = 1.0
        return CorrelationMatrix(variables=names, matrix=zero)

    stacked = np.vstack(arrays)
    with np.errstate(invalid="ignore"):
        corr = np.atleast_2d(np.corrcoef(stacked))
    corr = np.nan_to_num(corr, nan=0.0)
    matrix: list[list[float]] = [
        [round(float(v), 4) for v in row] for row in corr.tolist()
    ]
    return CorrelationMatrix(variables=names, matrix=matrix)
