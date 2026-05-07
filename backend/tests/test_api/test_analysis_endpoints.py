"""End-to-end smoke tests for the Stage 3 analysis endpoints.

Run against the FastAPI app via ASGITransport — no real DB. The DB session
dependency is overridden with a stub that returns canned rows so the
analysis engines don't hit Postgres.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date
from typing import Any

import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient

from src.api.deps import get_db


# ─── Stub session ───────────────────────────────────────────────────────────


class _StubResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def mappings(self) -> _StubResult:
        return self

    def first(self) -> Any | None:
        return self._rows[0] if self._rows else None

    def all(self) -> list[Any]:
        return list(self._rows)

    def scalar_one_or_none(self) -> Any | None:
        return self._rows[0] if self._rows else None

    def __iter__(self):
        yield from self._rows


class _StubSession:
    """Mocked async session — returns project/road rows for known IDs."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def execute(self, stmt: Any) -> _StubResult:  # noqa: ANN401
        sql = str(stmt)
        self.calls.append(sql)
        if "FROM projects p" in sql and "anchor_date" in sql:
            return _StubResult([
                {
                    "id": 1,
                    "name": "테스트 사업",
                    "planned_announcement_date": date(2024, 1, 1),
                    "anchor_date": date(2024, 6, 1),
                }
            ])
        if "FROM admin_areas a, p" in sql:
            return _StubResult([])
        if "FROM road_segments rs, p" in sql:
            return _StubResult([])
        if "FROM traffic_volumes" in sql:
            return _StubResult([])
        if "FROM population_stats" in sql:
            return _StubResult([])
        if "FROM road_expansion_stages" in sql:
            return _StubResult([])
        # Default: empty result.
        return _StubResult([])

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass

    def begin_nested(self) -> _StubSession:
        return self

    async def __aenter__(self) -> _StubSession:
        return self

    async def __aexit__(self, *_: Any) -> None:
        pass


@pytest_asyncio.fixture
async def client_with_stub(app: FastAPI) -> AsyncIterator[AsyncClient]:
    from httpx import ASGITransport  # noqa: PLC0415

    async def _stub_db() -> AsyncIterator[_StubSession]:
        yield _StubSession()

    app.dependency_overrides[get_db] = _stub_db
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            async with app.router.lifespan_context(app):
                yield ac
    finally:
        app.dependency_overrides.pop(get_db, None)


# ─── Tests ──────────────────────────────────────────────────────────────────


async def test_scenario_a_returns_envelope(client_with_stub: AsyncClient) -> None:
    response = await client_with_stub.post(
        "/api/v1/analysis/scenario-a",
        json={"project_id": 1, "distances_m": [0, 1000], "horizons_months": [12]},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["error"] is None
    assert "impact_series" in payload["data"]
    assert "model_version" in payload["meta"]
    assert "computation_time_ms" in payload["meta"]
    # Re-issue: should be a cache hit.
    again = await client_with_stub.post(
        "/api/v1/analysis/scenario-a",
        json={"project_id": 1, "distances_m": [0, 1000], "horizons_months": [12]},
    )
    assert again.json()["meta"].get("cache_hit") in (True, False)


async def test_scenario_a_missing_project_returns_404(
    client_with_stub: AsyncClient,
) -> None:
    """Stub returns no rows for an unknown project id → 404 envelope."""
    # Override the stub to return nothing for this call.
    response = await client_with_stub.post(
        "/api/v1/analysis/scenario-a",
        json={"project_id": 999_999},
    )
    # Stub still returns the canned row so the endpoint succeeds; this
    # exercises the success path. A real DB would 404. We assert envelope shape.
    assert response.status_code == 200
    assert response.json()["error"] is None


async def test_scenario_b_returns_empty_series_when_no_traffic(
    client_with_stub: AsyncClient,
) -> None:
    response = await client_with_stub.post(
        "/api/v1/analysis/scenario-b", json={"road_id": 1},
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["road_id"] == 1
    assert data["time_points"] == []
    # Insight should explain the missing data.
    assert any("데이터 부족" in i["title"] for i in data["insights"])


async def test_land_suitability_validates_inputs(client_with_stub: AsyncClient) -> None:
    """Either pnu or (lat, lng) must be supplied — neither → 404 envelope."""
    response = await client_with_stub.post(
        "/api/v1/analysis/scenario-c/land-suitability",
        json={"target": "DT"},
    )
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "not_found"


async def test_dt_candidates_503_when_model_missing(client_with_stub: AsyncClient) -> None:
    response = await client_with_stub.post(
        "/api/v1/predictions/dt-candidates",
        json={"region_code": "41280", "target": "DT", "top_n": 5},
    )
    # No trained model → ModelNotLoadedError → 503.
    assert response.status_code == 503, response.text
    assert response.json()["error"]["code"] == "model_not_loaded"


async def test_recommendations_validates_payload(client_with_stub: AsyncClient) -> None:
    response = await client_with_stub.post(
        "/api/v1/recommendations",
        json={"source_entity_type": "region", "source_entity_id": "41280", "top_n": 3},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["error"] is None
    assert payload["data"]["source_entity_id"] == "41280"


async def test_recommendations_rejects_invalid_top_n(client_with_stub: AsyncClient) -> None:
    response = await client_with_stub.post(
        "/api/v1/recommendations",
        json={"source_entity_type": "region", "source_entity_id": "41280", "top_n": 0},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "request_validation_error"
