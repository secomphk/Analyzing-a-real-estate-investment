"""Shared response envelope and pagination primitives.

Every successful response is wrapped in :class:`Envelope` so clients can
discriminate between data and error payloads with a single shape:

    { "data": <T>, "meta": {...}, "error": null }
"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class Meta(BaseModel):
    """Free-form metadata block (pagination cursors, scope tags, run ids…)."""

    model_config = ConfigDict(extra="allow")


class ErrorPayload(BaseModel):
    """Error body returned in the envelope when ``error`` is non-null."""

    code: str
    message: str
    details: dict[str, object] | None = None


class Envelope(BaseModel, Generic[T]):
    """Standard response envelope.

    Routes return ``Envelope[Foo]`` (or a plain dict matching this shape).
    Error responses are produced by the global exception handlers; they
    follow the same shape with ``data=None`` and a populated ``error``.
    """

    data: T | None = None
    meta: Meta = Field(default_factory=Meta)
    error: ErrorPayload | None = None


class Pagination(BaseModel):
    """Cursor-style pagination metadata (used inside ``Meta``)."""

    total: int = 0
    limit: int = 50
    offset: int = 0
    next_cursor: str | None = None
