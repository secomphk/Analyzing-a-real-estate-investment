import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

// Default handlers — every test gets these unless it overrides via
// ``server.use(...)``. The shapes match the backend envelope contract.
const ok = <T>(data: T, meta: Record<string, unknown> = {}) =>
  HttpResponse.json({ data, meta, error: null });

export const handlers = [
  http.get("/api/v1/projects", () =>
    ok([
      {
        id: 1,
        name: "한강2 공공주택지구",
        project_type: "public_housing",
        region_code: "41280",
        area_ha: 731,
        expected_compensation_billion_krw: 6800,
        planned_announcement_date: "2023-11-15",
        planned_completion_date: "2031-12-31",
        stage_count: 3,
      },
    ]),
  ),
  http.get("/api/v1/projects/:id", () =>
    ok({
      id: 1,
      name: "한강2 공공주택지구",
      project_type: "public_housing",
      region_code: "41280",
      area_ha: 731,
      expected_compensation_billion_krw: 6800,
      planned_announcement_date: "2023-11-15",
      planned_completion_date: "2031-12-31",
      description: "Test fixture",
      source: "test",
      stages: [
        { id: 1, stage: "announced", occurred_at: "2023-11-15" },
        { id: 2, stage: "designated", occurred_at: "2024-08-30" },
      ],
    }),
  ),
  http.get("/api/v1/roads", () =>
    ok([
      {
        id: 1,
        name: "평택 만세로",
        route_no: "지방도 70호",
        region_code: "41220",
        length_m: 7600,
        stage_count: 4,
      },
    ]),
  ),
  http.get("/api/v1/stores", () =>
    ok([
      {
        id: 11,
        name: "평택비전DT점",
        address: "경기 평택시 비전동",
        region_code: "4122010100",
        pnu: "4122010100100090090",
        store_type: "DT",
        opened_at: "2019-02-14",
        closed_at: null,
        land_area_m2: 1510,
        building_area_m2: 295,
        brand_name: "스타벅스",
        brand_category: "cafe",
      },
    ]),
  ),
  http.post("/api/v1/analysis/scenario-a", async () =>
    ok(
      {
        project_id: 1,
        anchor_date: "2025-06-01",
        impact_series: [
          {
            distance_m: 0,
            points: [
              { distance_m: 0, months_after_anchor: 0, expected_uplift_pct: 0.18, confidence: 0.7 },
              { distance_m: 0, months_after_anchor: 12, expected_uplift_pct: 0.21, confidence: 0.7 },
            ],
          },
        ],
        zones: [{ admin_code: "4128010500", admin_name: "운양동", distance_m: 1200 }],
        roads: [],
      },
      { model_version: "scenario_a_v1.0.0", confidence_score: 0.6, cache_hit: false, computation_time_ms: 12 },
    ),
  ),
  http.post("/api/v1/analysis/scenario-b", async () =>
    ok(
      {
        road_id: 1,
        time_points: [
          { year_month: "2024-01", population: 32000, aadt: 12500, road_progress: 0.6 },
          { year_month: "2024-02", population: 32100, aadt: 12700, road_progress: 0.6 },
        ],
        correlation_variables: ["road_progress", "population", "aadt"],
        correlation_matrix: [
          [1, 0.6, 0.7],
          [0.6, 1, 0.5],
          [0.7, 0.5, 1],
        ],
        lead_lag: { a: "population", b: "aadt", best_lag_months: -2, best_correlation: 0.62, classification: "coincident" },
        insights: [{ title: "샘플", detail: "테스트", score: 0.5 }],
      },
      { model_version: "scenario_b_v1.0.0", confidence_score: 0.7 },
    ),
  ),
  http.post("/api/v1/analysis/scenario-c/store-impact", async () =>
    ok(
      {
        store_id: 11,
        open_date: "2019-02-14",
        bands: [
          { band_m: 500, horizon: "+1y", pre_avg_price_per_m2: 1_000_000, post_avg_price_per_m2: 1_180_000, change_pct: 0.18, baseline_pct: 0.06, halo_pct: 0.12, sample_pre: 4, sample_post: 4 },
          { band_m: 500, horizon: "+3y", pre_avg_price_per_m2: 1_000_000, post_avg_price_per_m2: 1_320_000, change_pct: 0.32, baseline_pct: 0.15, halo_pct: 0.17, sample_pre: 4, sample_post: 6 },
        ],
      },
      { model_version: "scenario_c_v1.0.0", confidence_score: 0.65 },
    ),
  ),
  http.post("/api/v1/analysis/scenario-c/land-suitability", async () =>
    ok(
      {
        pnu: "4128010500100010000",
        target: "DT",
        score_raw: 0.78,
        score_100: 78,
        label: "high",
        rationales: [
          { category: "property", impact: "positive", feature: "land_area_m2", value: 1500, detail: "부지 충분" },
          { category: "traffic", impact: "positive", feature: "aadt_nearest_road", value: 15000, detail: "통행량 충분" },
        ],
        value_forecast: { "1y": 0.06, "3y": 0.18, "5y": 0.32 },
      },
      { model_version: "scenario_c_v1.0.0", confidence_score: 0.7, top_factors: [
        { factor: "aadt_nearest_road", value: 15000, impact: "positive", shap: 0.4 },
      ] },
    ),
  ),
  http.post("/api/v1/predictions/dt-candidates", async () =>
    ok(
      {
        region_code: "41280",
        target: "DT",
        candidates: [
          {
            pnu: "4128010500100010000",
            address: "운양동",
            suitability: { score_raw: 0.82, score_100: 82, label: "high", target: "DT" },
            value_forecast: { forecast: { "1y": 0.06, "3y": 0.2, "5y": 0.34 } },
            rationales: [],
            similar_stores: [],
          },
        ],
      },
      { model_version: "scenario_c_v1.0.0", confidence_score: 0.75 },
    ),
  ),
  http.post("/api/v1/recommendations", async () =>
    ok(
      {
        source_entity_type: "region",
        source_entity_id: "41280",
        items: [
          { target_entity_type: "region", target_entity_id: "41220", target_label: "평택시", score: 0.81, rank: 1 },
        ],
      },
      { model_version: "similarity_v1.0.0" },
    ),
  ),
];

export const server = setupServer(...handlers);
