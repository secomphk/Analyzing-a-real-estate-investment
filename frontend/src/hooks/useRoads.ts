import { useQuery } from "@tanstack/react-query";

import { getRoad, listRoads, type ListRoadsParams } from "@/api/roads";
import { runScenarioB, type ScenarioBInput } from "@/api/analysis";

export function useRoadList(params: ListRoadsParams = {}) {
  return useQuery({
    queryKey: ["roads", params],
    queryFn: () => listRoads(params),
  });
}

export function useRoad(roadId: number | null | undefined) {
  return useQuery({
    queryKey: ["road", roadId],
    queryFn: () => getRoad(roadId as number),
    enabled: typeof roadId === "number",
  });
}

export function useScenarioB(input: ScenarioBInput | null) {
  return useQuery({
    queryKey: ["scenario-b", input],
    queryFn: () => runScenarioB(input as ScenarioBInput),
    enabled: !!input?.road_id,
  });
}
