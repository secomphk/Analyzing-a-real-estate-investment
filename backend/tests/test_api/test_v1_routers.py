"""Smoke test for legacy / dummy routes that are still envelope-only.

After Stage 3, most endpoints became real implementations that talk to the
DB. The routes verified here are the ones that intentionally remain stubs
(deprecated GET aliases, ``/analysis/runs`` listing, revenue forecast).
The full Stage-3 routes are exercised by ``test_analysis_endpoints.py``.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

DEPRECATED_OR_STUB_ROUTES = [
    # Still listing-stubs until Stage 4 — return an envelope with meta.status.
    ("GET", "/api/v1/analysis/runs"),
    ("GET", "/api/v1/analysis/runs/abc"),
    ("GET", "/api/v1/analysis/runs/abc/results"),
    ("GET", "/api/v1/stores/1/similar"),
    ("POST", "/api/v1/predictions/suitability/dt"),
    ("POST", "/api/v1/predictions/suitability/di"),
    ("POST", "/api/v1/predictions/revenue/forecast"),
]


@pytest.mark.parametrize(("method", "path"), DEPRECATED_OR_STUB_ROUTES)
async def test_legacy_route_returns_envelope(
    client: AsyncClient, method: str, path: str
) -> None:
    response = await client.request(method, path)
    assert response.status_code in (200, 202, 303), (
        f"{method} {path} → {response.status_code}"
    )
    payload = response.json()
    assert set(payload.keys()) >= {"data", "meta", "error"}
    assert payload["error"] is None
    # Either still-not-implemented (analysis runs) or deprecated alias.
    status_field = payload["meta"].get("status")
    assert status_field in {"not_implemented", "deprecated"}, (
        f"unexpected meta.status={status_field!r} for {method} {path}"
    )
