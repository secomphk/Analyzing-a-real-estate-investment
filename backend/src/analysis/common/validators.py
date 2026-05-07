"""Input validators used by analysis engines.

Translate `bad input → 422` so handlers don't need to repeat the same
checks. Raise :class:`AnalysisInputError` (subclass of
:class:`src.core.exceptions.ValidationError`) so the global handler maps
it to the standard envelope automatically.
"""

from __future__ import annotations

import re
from collections.abc import Sized
from datetime import date

from src.core.exceptions import ValidationError as _ValidationError


class AnalysisInputError(_ValidationError):
    """Raised when an analysis is called with malformed inputs."""


_PNU_RE = re.compile(r"^\d{19}$")


def validate_pnu(pnu: str) -> str:
    """Accept either ``"1234567890123456789"`` or ``"1234567890-1-0001-0000"``.

    Returns the canonical 19-digit form.
    """
    cleaned = pnu.replace("-", "")
    if not _PNU_RE.fullmatch(cleaned):
        raise AnalysisInputError(f"Invalid PNU: {pnu!r} — expected 19 digits.")
    return cleaned


def validate_coordinate(lat: float, lng: float) -> tuple[float, float]:
    """Confirm a (lat, lng) pair lies within Korea's broad lat/lng box.

    Tightening the bounds keeps obvious junk like swapped (lng, lat)
    arguments from silently producing nonsense distances.
    """
    if not (32.0 <= lat <= 39.0):
        raise AnalysisInputError(f"Latitude out of Korea range: {lat}")
    if not (124.0 <= lng <= 132.0):
        raise AnalysisInputError(f"Longitude out of Korea range: {lng}")
    return lat, lng


def validate_date_range(start: date, end: date) -> tuple[date, date]:
    """Reject inverted or zero-length ranges."""
    if start > end:
        raise AnalysisInputError(f"Date range inverted: {start} > {end}")
    return start, end


def require_non_empty(value: Sized, *, what: str) -> None:
    """Raise if ``value`` is empty (``len()`` zero)."""
    if len(value) == 0:
        raise AnalysisInputError(f"{what} is empty.")
