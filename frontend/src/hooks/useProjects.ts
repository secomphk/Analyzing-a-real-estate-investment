import { useQuery } from "@tanstack/react-query";

import {
  getProject,
  listProjects,
  type ListProjectsParams,
} from "@/api/projects";
import { runScenarioA, type ScenarioAInput } from "@/api/analysis";

export function useProjectList(params: ListProjectsParams = {}) {
  return useQuery({
    queryKey: ["projects", params],
    queryFn: () => listProjects(params),
  });
}

export function useProject(projectId: number | null | undefined) {
  return useQuery({
    queryKey: ["project", projectId],
    queryFn: () => getProject(projectId as number),
    enabled: typeof projectId === "number",
  });
}

export function useScenarioA(input: ScenarioAInput | null) {
  return useQuery({
    queryKey: ["scenario-a", input],
    queryFn: () => runScenarioA(input as ScenarioAInput),
    enabled: !!input?.project_id,
  });
}
