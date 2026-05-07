"""Locust load test driver for the Stage 5 perf gate.

Usage::

    poetry run locust -f scripts/load_test.py \\
        --host=https://api-staging.example.com \\
        --users=50 --spawn-rate=10 --run-time=5m \\
        --headless --csv=load_results

Goals (from the Stage 5 spec):
- 동시 50명, 5분 — 시나리오 A·B·C 호출 비율 그대로
- P95 응답 < 5s
- 에러율 < 0.1 %

The IDs/region codes default to the seed data so the test runs against a
freshly-seeded staging DB. Override via env vars:
  ``LT_PROJECT_ID``  default 1
  ``LT_ROAD_ID``     default 1
  ``LT_STORE_ID``    default 11
  ``LT_PNU``         default "4128010500100010000"
  ``LT_REGION_CODE`` default "41280"
"""

from __future__ import annotations

import os
import random

from locust import HttpUser, between, task


PROJECT_ID = int(os.getenv("LT_PROJECT_ID", "1"))
ROAD_ID = int(os.getenv("LT_ROAD_ID", "1"))
STORE_ID = int(os.getenv("LT_STORE_ID", "11"))
PNU = os.getenv("LT_PNU", "4128010500100010000")
REGION_CODE = os.getenv("LT_REGION_CODE", "41280")


class AnalystUser(HttpUser):
    """Simulates an analyst flipping between scenarios."""

    # Realistic "think time" — between requests on the same user.
    wait_time = between(0.5, 2.0)

    # ─── Scenario A (weight 3) ──────────────────────────────────────────

    @task(3)
    def scenario_a(self) -> None:
        self.client.post(
            "/api/v1/analysis/scenario-a",
            json={"project_id": PROJECT_ID},
            name="POST /analysis/scenario-a",
            timeout=10,
        )

    # ─── Scenario B (weight 3) ──────────────────────────────────────────

    @task(3)
    def scenario_b(self) -> None:
        self.client.post(
            "/api/v1/analysis/scenario-b",
            json={"road_id": ROAD_ID},
            name="POST /analysis/scenario-b",
            timeout=10,
        )

    # ─── Scenario C — store impact (weight 2) ───────────────────────────

    @task(2)
    def store_impact(self) -> None:
        self.client.post(
            "/api/v1/analysis/scenario-c/store-impact",
            json={"store_id": STORE_ID},
            name="POST /analysis/scenario-c/store-impact",
            timeout=10,
        )

    # ─── Scenario C — land suitability (weight 2) ──────────────────────

    @task(2)
    def land_suitability(self) -> None:
        target = random.choice(["DT", "DI"])
        self.client.post(
            "/api/v1/analysis/scenario-c/land-suitability",
            json={"pnu": PNU, "target": target},
            name="POST /analysis/scenario-c/land-suitability",
            timeout=10,
        )

    # ─── Scenario C — DT candidates (weight 1, heaviest) ────────────────

    @task(1)
    def dt_candidates(self) -> None:
        self.client.post(
            "/api/v1/predictions/dt-candidates",
            json={"region_code": REGION_CODE, "target": "DT", "top_n": 10},
            name="POST /predictions/dt-candidates",
            timeout=15,
        )

    # ─── Catalog reads (weight 4 — typical browse mix) ─────────────────

    @task(4)
    def list_pages(self) -> None:
        self.client.get("/api/v1/projects?limit=20", name="GET /projects")
        self.client.get("/api/v1/roads?limit=20", name="GET /roads")
        self.client.get("/api/v1/stores?limit=20", name="GET /stores")

    # ─── Recommendations (weight 1) ────────────────────────────────────

    @task(1)
    def recommendations(self) -> None:
        self.client.post(
            "/api/v1/recommendations",
            json={
                "source_entity_type": "region",
                "source_entity_id": REGION_CODE,
                "top_n": 10,
            },
            name="POST /recommendations",
            timeout=10,
        )
