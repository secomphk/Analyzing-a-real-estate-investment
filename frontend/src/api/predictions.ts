import { apiClient, callJson } from "./client";
import {
  DTCandidatesEnvelope,
  type DTCandidatesResponse,
} from "./schemas";

export interface DTCandidatesInput {
  region_code: string;
  target?: "DT" | "DI";
  top_n?: number;
}

export async function dtCandidates(body: DTCandidatesInput) {
  return callJson<DTCandidatesResponse>(DTCandidatesEnvelope, () =>
    apiClient
      .post("/api/v1/predictions/dt-candidates", body)
      .then((r) => r.data),
  );
}
