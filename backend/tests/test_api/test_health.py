"""Smoke test: /health responds 200 in the standard envelope shape."""

from __future__ import annotations

from httpx import AsyncClient


async def test_health_returns_envelope(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert set(payload.keys()) >= {"data", "meta", "error"}
    assert payload["error"] is None
    assert payload["data"]["status"] == "ok"


async def test_health_sets_request_id_header(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert "x-request-id" in response.headers
    assert "x-process-time-ms" in response.headers


async def test_root_returns_envelope(client: AsyncClient) -> None:
    response = await client.get("/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["service"]
    assert payload["error"] is None
