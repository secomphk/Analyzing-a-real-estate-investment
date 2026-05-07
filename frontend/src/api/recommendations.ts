import { apiClient, callJson } from "./client";
import {
  RecommendationsEnvelope,
  type RecommendationsResponse,
} from "./schemas";

export interface RecommendationsInput {
  source_entity_type: "region" | "store";
  source_entity_id: string;
  top_n?: number;
}

export async function getRecommendations(body: RecommendationsInput) {
  return callJson<RecommendationsResponse>(RecommendationsEnvelope, () =>
    apiClient
      .post("/api/v1/recommendations", body)
      .then((r) => r.data),
  );
}
