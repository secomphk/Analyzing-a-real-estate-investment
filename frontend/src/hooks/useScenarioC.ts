import { useQuery } from "@tanstack/react-query";

import {
  runLandSuitability,
  runStoreImpact,
  type LandSuitabilityInput,
  type StoreImpactInput,
} from "@/api/analysis";
import { dtCandidates, type DTCandidatesInput } from "@/api/predictions";

export function useStoreImpact(input: StoreImpactInput | null) {
  return useQuery({
    queryKey: ["store-impact", input],
    queryFn: () => runStoreImpact(input as StoreImpactInput),
    enabled: !!input?.store_id,
  });
}

export function useLandSuitability(input: LandSuitabilityInput | null) {
  return useQuery({
    queryKey: ["land-suitability", input],
    queryFn: () => runLandSuitability(input as LandSuitabilityInput),
    enabled: !!input && (!!input.pnu || (input.lat != null && input.lng != null)),
  });
}

export function useDTCandidates(input: DTCandidatesInput | null) {
  return useQuery({
    queryKey: ["dt-candidates", input],
    queryFn: () => dtCandidates(input as DTCandidatesInput),
    enabled: !!input?.region_code,
  });
}
