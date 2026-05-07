"""Smoke test: OpenAPI / Swagger surface is reachable and registers all routers."""

from __future__ import annotations

from httpx import AsyncClient


async def test_docs_html(client: AsyncClient) -> None:
    response = await client.get("/docs")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")


async def test_openapi_lists_all_v1_prefixes(client: AsyncClient) -> None:
    response = await client.get("/api/v1/openapi.json")
    assert response.status_code == 200
    paths = set(response.json()["paths"].keys())
    expected_prefixes = {
        "/api/v1/projects",
        "/api/v1/roads",
        "/api/v1/stores",
        "/api/v1/analysis",
        "/api/v1/recommendations",
        "/api/v1/predictions",
    }
    for prefix in expected_prefixes:
        assert any(p.startswith(prefix) for p in paths), f"missing routes for {prefix}"
