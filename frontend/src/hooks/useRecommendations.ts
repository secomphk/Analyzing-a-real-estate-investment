import { useQuery } from "@tanstack/react-query";

import {
  getRecommendations,
  type RecommendationsInput,
} from "@/api/recommendations";

export function useRecommendations(input: RecommendationsInput | null) {
  return useQuery({
    queryKey: ["recommendations", input],
    queryFn: () => getRecommendations(input as RecommendationsInput),
    enabled: !!input?.source_entity_id,
  });
}
