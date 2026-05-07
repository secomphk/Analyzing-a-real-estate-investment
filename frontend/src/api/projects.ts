import { apiClient, callJson } from "./client";
import {
  ProjectDetailEnvelope,
  ProjectListEnvelope,
  type ProjectDetail,
  type ProjectSummary,
} from "./schemas";

export interface ListProjectsParams {
  region_code?: string;
  limit?: number;
  offset?: number;
}

export async function listProjects(params: ListProjectsParams = {}) {
  return callJson<ProjectSummary[]>(ProjectListEnvelope, () =>
    apiClient
      .get("/api/v1/projects", { params })
      .then((r) => r.data),
  );
}

export async function getProject(projectId: number) {
  return callJson<ProjectDetail>(ProjectDetailEnvelope, () =>
    apiClient.get(`/api/v1/projects/${projectId}`).then((r) => r.data),
  );
}
