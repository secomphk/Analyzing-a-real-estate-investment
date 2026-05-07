import { apiClient, callJson } from "./client";
import {
  RoadDetailEnvelope,
  RoadListEnvelope,
  type RoadDetail,
  type RoadSummary,
} from "./schemas";

export interface ListRoadsParams {
  region_code?: string;
  limit?: number;
  offset?: number;
}

export async function listRoads(params: ListRoadsParams = {}) {
  return callJson<RoadSummary[]>(RoadListEnvelope, () =>
    apiClient.get("/api/v1/roads", { params }).then((r) => r.data),
  );
}

export async function getRoad(roadId: number) {
  return callJson<RoadDetail>(RoadDetailEnvelope, () =>
    apiClient.get(`/api/v1/roads/${roadId}`).then((r) => r.data),
  );
}
