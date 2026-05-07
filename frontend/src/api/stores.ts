import { apiClient, callJson } from "./client";
import {
  StoreDetailEnvelope,
  StoreListEnvelope,
  type StoreDetail,
  type StoreSummary,
} from "./schemas";

export interface ListStoresParams {
  brand?: string;
  store_type?: "DT" | "DI" | "standard" | "kiosk";
  region_code?: string;
  limit?: number;
  offset?: number;
}

export async function listStores(params: ListStoresParams = {}) {
  return callJson<StoreSummary[]>(StoreListEnvelope, () =>
    apiClient.get("/api/v1/stores", { params }).then((r) => r.data),
  );
}

export async function getStore(storeId: number) {
  return callJson<StoreDetail>(StoreDetailEnvelope, () =>
    apiClient.get(`/api/v1/stores/${storeId}`).then((r) => r.data),
  );
}
