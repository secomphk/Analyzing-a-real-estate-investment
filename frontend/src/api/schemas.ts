import { z } from "zod";

// ─── Envelope ───────────────────────────────────────────────────────────────

// Stage 1+ contract: every backend response is wrapped in this shape.
// Errors flip ``data`` to null and populate ``error``; successful payloads
// always carry data and a meta block.
export const Meta = z
  .object({
    cache_hit: z.boolean().optional(),
    computation_time_ms: z.number().optional(),
    model_version: z.string().optional(),
    confidence_score: z.number().optional(),
    top_factors: z
      .array(
        z.object({
          factor: z.string(),
          value: z.unknown(),
          impact: z.enum(["positive", "negative", "neutral"]).optional(),
          explanation: z.string().optional(),
          shap: z.number().nullable().optional(),
        }),
      )
      .optional(),
    notes: z.array(z.string()).optional(),
  })
  .passthrough();
export type Meta = z.infer<typeof Meta>;

export const ErrorPayload = z.object({
  code: z.string(),
  message: z.string(),
  details: z.record(z.unknown()).optional(),
});
export type ErrorPayload = z.infer<typeof ErrorPayload>;

export const envelope = <T extends z.ZodTypeAny>(data: T) =>
  z.object({
    data: data.nullable(),
    meta: Meta.optional().default({}),
    error: ErrorPayload.nullable().optional(),
  });

// ─── Scenario A ─────────────────────────────────────────────────────────────

export const ScenarioAImpactPoint = z.object({
  distance_m: z.number(),
  months_after_anchor: z.number().int(),
  expected_uplift_pct: z.number(),
  confidence: z.number(),
});
export type ScenarioAImpactPoint = z.infer<typeof ScenarioAImpactPoint>;

export const ScenarioAImpactSeries = z.object({
  distance_m: z.number(),
  points: z.array(ScenarioAImpactPoint),
});
export type ScenarioAImpactSeries = z.infer<typeof ScenarioAImpactSeries>;

export const ScenarioAZone = z.object({
  admin_code: z.string(),
  admin_name: z.string(),
  distance_m: z.number(),
});
export type ScenarioAZone = z.infer<typeof ScenarioAZone>;

export const ScenarioARoad = z.object({
  road_id: z.number().int(),
  name: z.string(),
  route_no: z.string().nullable(),
  length_m: z.number().nullable(),
  distance_m: z.number(),
  weight: z.number(),
});
export type ScenarioARoad = z.infer<typeof ScenarioARoad>;

export const ScenarioAResponse = z.object({
  project_id: z.number(),
  anchor_date: z.string(),
  impact_series: z.array(ScenarioAImpactSeries),
  zones: z.array(ScenarioAZone),
  roads: z.array(ScenarioARoad),
});
export type ScenarioAResponse = z.infer<typeof ScenarioAResponse>;

export const ScenarioAEnvelope = envelope(ScenarioAResponse);

// ─── Scenario B ─────────────────────────────────────────────────────────────

export const ScenarioBTimePoint = z.object({
  year_month: z.string(),
  population: z.number().nullable(),
  aadt: z.number().nullable(),
  road_progress: z.number(),
});
export type ScenarioBTimePoint = z.infer<typeof ScenarioBTimePoint>;

export const ScenarioBLeadLag = z.object({
  a: z.string(),
  b: z.string(),
  best_lag_months: z.number().int(),
  best_correlation: z.number(),
  classification: z.enum(["leading", "coincident", "lagging", "uncertain"]),
});
export type ScenarioBLeadLag = z.infer<typeof ScenarioBLeadLag>;

export const ScenarioBInsight = z.object({
  title: z.string(),
  detail: z.string(),
  score: z.number(),
});
export type ScenarioBInsight = z.infer<typeof ScenarioBInsight>;

export const ScenarioBResponse = z.object({
  road_id: z.number(),
  time_points: z.array(ScenarioBTimePoint),
  correlation_variables: z.array(z.string()),
  correlation_matrix: z.array(z.array(z.number())),
  lead_lag: ScenarioBLeadLag.nullable(),
  insights: z.array(ScenarioBInsight),
});
export type ScenarioBResponse = z.infer<typeof ScenarioBResponse>;

export const ScenarioBEnvelope = envelope(ScenarioBResponse);

// ─── Stores (catalogue + impact) ───────────────────────────────────────────

export const StoreSummary = z.object({
  id: z.number().int(),
  name: z.string(),
  address: z.string().nullable(),
  region_code: z.string().nullable(),
  pnu: z.string().nullable(),
  store_type: z.string(),
  opened_at: z.string().nullable(),
  closed_at: z.string().nullable(),
  land_area_m2: z.number().nullable(),
  building_area_m2: z.number().nullable(),
  brand_name: z.string(),
  brand_category: z.string(),
});
export type StoreSummary = z.infer<typeof StoreSummary>;

export const StoreDetail = StoreSummary.extend({
  lat: z.number().nullable().optional(),
  lng: z.number().nullable().optional(),
});
export type StoreDetail = z.infer<typeof StoreDetail>;

export const StoreListEnvelope = envelope(z.array(StoreSummary));
export const StoreDetailEnvelope = envelope(StoreDetail);

export const StoreImpactBand = z.object({
  band_m: z.number().int(),
  horizon: z.enum(["+1y", "+3y", "+5y"]),
  pre_avg_price_per_m2: z.number().nullable(),
  post_avg_price_per_m2: z.number().nullable(),
  change_pct: z.number().nullable(),
  baseline_pct: z.number().nullable(),
  halo_pct: z.number().nullable(),
  sample_pre: z.number(),
  sample_post: z.number(),
});
export type StoreImpactBand = z.infer<typeof StoreImpactBand>;

export const StoreImpactResponse = z.object({
  store_id: z.number(),
  open_date: z.string(),
  bands: z.array(StoreImpactBand),
});
export type StoreImpactResponse = z.infer<typeof StoreImpactResponse>;
export const StoreImpactEnvelope = envelope(StoreImpactResponse);

// ─── Land suitability + DT candidates ──────────────────────────────────────

export const Rationale = z.object({
  category: z.enum(["property", "surroundings", "traffic", "catalyst"]),
  impact: z.enum(["positive", "negative", "neutral"]),
  feature: z.string(),
  value: z.number(),
  detail: z.string(),
});
export type Rationale = z.infer<typeof Rationale>;

export const LandSuitabilityResponse = z.object({
  pnu: z.string().nullable(),
  target: z.enum(["DT", "DI"]),
  score_raw: z.number(),
  score_100: z.number(),
  label: z.enum(["low", "medium", "high"]),
  rationales: z.array(Rationale),
  value_forecast: z.record(z.number()).nullable().optional(),
});
export type LandSuitabilityResponse = z.infer<typeof LandSuitabilityResponse>;
export const LandSuitabilityEnvelope = envelope(LandSuitabilityResponse);

export const Candidate = z
  .object({
    pnu: z.string(),
    address: z.string().nullable(),
    suitability: z.object({
      score_raw: z.number(),
      score_100: z.number(),
      label: z.enum(["low", "medium", "high"]),
      target: z.enum(["DT", "DI"]),
    }),
    value_forecast: z
      .object({
        forecast: z.record(z.number()),
        base_year: z.number().optional(),
        base_price_per_m2: z.number().optional(),
        confidence_score: z.number().optional(),
      })
      .nullable()
      .optional(),
    similar_stores: z
      .array(
        z.object({
          store_id: z.number(),
          score: z.number(),
          rank: z.number(),
        }),
      )
      .optional(),
    rationales: z.array(Rationale).optional(),
    breakdown: z.record(z.unknown()).optional(),
  })
  .passthrough();
export type Candidate = z.infer<typeof Candidate>;

export const DTCandidatesResponse = z.object({
  region_code: z.string(),
  target: z.enum(["DT", "DI"]),
  candidates: z.array(Candidate),
});
export type DTCandidatesResponse = z.infer<typeof DTCandidatesResponse>;
export const DTCandidatesEnvelope = envelope(DTCandidatesResponse);

// ─── Recommendations ───────────────────────────────────────────────────────

export const RecommendationItem = z.object({
  target_entity_type: z.string(),
  target_entity_id: z.string(),
  target_label: z.string().nullable().optional(),
  score: z.number(),
  rank: z.number().int(),
  breakdown: z.record(z.unknown()).optional(),
});
export type RecommendationItem = z.infer<typeof RecommendationItem>;

export const RecommendationsResponse = z.object({
  source_entity_type: z.string(),
  source_entity_id: z.string(),
  items: z.array(RecommendationItem),
});
export type RecommendationsResponse = z.infer<typeof RecommendationsResponse>;
export const RecommendationsEnvelope = envelope(RecommendationsResponse);

// ─── Projects + Roads (read endpoints) ─────────────────────────────────────

export const ProjectStage = z.object({
  id: z.number(),
  stage: z.string(),
  occurred_at: z.string(),
  sequence_no: z.number().nullable().optional(),
  note: z.string().nullable().optional(),
  source: z.string().nullable().optional(),
});
export type ProjectStage = z.infer<typeof ProjectStage>;

export const ProjectSummary = z
  .object({
    id: z.number(),
    name: z.string(),
    project_type: z.string(),
    region_code: z.string().nullable(),
    area_ha: z.number().nullable(),
    expected_compensation_billion_krw: z.number().nullable(),
    planned_announcement_date: z.string().nullable(),
    planned_completion_date: z.string().nullable(),
    stage_count: z.number().optional(),
  })
  .passthrough();
export type ProjectSummary = z.infer<typeof ProjectSummary>;

export const ProjectDetail = ProjectSummary.extend({
  description: z.string().nullable().optional(),
  source: z.string().nullable().optional(),
  stages: z.array(ProjectStage),
});
export type ProjectDetail = z.infer<typeof ProjectDetail>;

export const ProjectListEnvelope = envelope(z.array(ProjectSummary));
export const ProjectDetailEnvelope = envelope(ProjectDetail);

export const RoadStage = z.object({
  id: z.number(),
  stage: z.string(),
  occurred_at: z.string(),
  lanes_before: z.number().nullable().optional(),
  lanes_after: z.number().nullable().optional(),
  width_before_m: z.number().nullable().optional(),
  width_after_m: z.number().nullable().optional(),
  note: z.string().nullable().optional(),
  source: z.string().nullable().optional(),
});
export type RoadStage = z.infer<typeof RoadStage>;

export const RoadSummary = z
  .object({
    id: z.number(),
    name: z.string(),
    route_no: z.string().nullable(),
    region_code: z.string().nullable(),
    length_m: z.number().nullable(),
    stage_count: z.number().optional(),
  })
  .passthrough();
export type RoadSummary = z.infer<typeof RoadSummary>;

export const RoadDetail = RoadSummary.extend({
  description: z.string().nullable().optional(),
  source: z.string().nullable().optional(),
  stages: z.array(RoadStage),
});
export type RoadDetail = z.infer<typeof RoadDetail>;

export const RoadListEnvelope = envelope(z.array(RoadSummary));
export const RoadDetailEnvelope = envelope(RoadDetail);
