import { apiClient, callJson } from "./client";
import {
  LandSuitabilityEnvelope,
  ScenarioAEnvelope,
  ScenarioBEnvelope,
  StoreImpactEnvelope,
  type LandSuitabilityResponse,
  type ScenarioAResponse,
  type ScenarioBResponse,
  type StoreImpactResponse,
} from "./schemas";

// ─── Scenario A ─────────────────────────────────────────────────────────────

export interface ScenarioAInput {
  project_id: number;
  distances_m?: number[];
  horizons_months?: number[];
  radius_m?: number;
}

export async function runScenarioA(body: ScenarioAInput) {
  return callJson<ScenarioAResponse>(ScenarioAEnvelope, () =>
    apiClient
      .post("/api/v1/analysis/scenario-a", body)
      .then((r) => r.data),
  );
}

// ─── Scenario B ─────────────────────────────────────────────────────────────

export interface ScenarioBInput {
  road_id: number;
  start?: string;
  end?: string;
}

export async function runScenarioB(body: ScenarioBInput) {
  return callJson<ScenarioBResponse>(ScenarioBEnvelope, () =>
    apiClient
      .post("/api/v1/analysis/scenario-b", body)
      .then((r) => r.data),
  );
}

// ─── Scenario C — store impact ─────────────────────────────────────────────

export interface StoreImpactInput {
  store_id: number;
  bands_m?: number[];
}

export async function runStoreImpact(body: StoreImpactInput) {
  return callJson<StoreImpactResponse>(StoreImpactEnvelope, () =>
    apiClient
      .post("/api/v1/analysis/scenario-c/store-impact", body)
      .then((r) => r.data),
  );
}

// ─── Scenario C — land suitability ─────────────────────────────────────────

export interface LandSuitabilityInput {
  pnu?: string;
  lat?: number;
  lng?: number;
  target?: "DT" | "DI";
  snapshot_date?: string;
}

export async function runLandSuitability(body: LandSuitabilityInput) {
  return callJson<LandSuitabilityResponse>(LandSuitabilityEnvelope, () =>
    apiClient
      .post("/api/v1/analysis/scenario-c/land-suitability", body)
      .then((r) => r.data),
  );
}
