import { useQuery } from "@tanstack/react-query";

import { getStore, listStores, type ListStoresParams } from "@/api/stores";

export function useStoreList(params: ListStoresParams = {}) {
  return useQuery({
    queryKey: ["stores", params],
    queryFn: () => listStores(params),
  });
}

export function useStore(storeId: number | null | undefined) {
  return useQuery({
    queryKey: ["store", storeId],
    queryFn: () => getStore(storeId as number),
    enabled: typeof storeId === "number",
  });
}
