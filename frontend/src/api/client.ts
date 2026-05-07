import axios, { AxiosError, type AxiosInstance } from "axios";
import { z } from "zod";

import { Meta, ErrorPayload } from "./schemas";

// Single shared axios instance. The dev server proxies /api/* to the backend
// (see vite.config.ts), so leaving VITE_API_URL empty is the right default
// during local development.
const baseURL = import.meta.env.VITE_API_URL ?? "";

export const apiClient: AxiosInstance = axios.create({
  baseURL,
  timeout: 10_000,
  headers: { Accept: "application/json" },
});

// Normalised, typed error surface that components can `instanceof`-check.
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details?: Record<string, unknown>;

  constructor(message: string, status: number, code = "unknown", details?: Record<string, unknown>) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

apiClient.interceptors.response.use(
  (response) => response,
  (raw: AxiosError) => {
    // Network / timeout — no envelope to parse.
    if (!raw.response) {
      return Promise.reject(
        new ApiError(raw.message || "Network error", 0, "network_error"),
      );
    }
    const { status, data } = raw.response;
    const parsed = z
      .object({ error: ErrorPayload.nullable().optional() })
      .safeParse(data);
    const err = parsed.success ? parsed.data.error : null;
    return Promise.reject(
      new ApiError(
        err?.message ?? raw.message ?? "Request failed",
        status,
        err?.code ?? `http_${status}`,
        err?.details,
      ),
    );
  },
);

// ─── Helpers ────────────────────────────────────────────────────────────────

export interface UnpackedResponse<T> {
  data: T;
  meta: z.infer<typeof Meta>;
}

/** Unwrap the standard envelope, throwing :class:`ApiError` on payloads that
 *  carry an error or fail validation. The caller gets a strongly-typed
 *  ``data`` plus the ``meta`` block (cache_hit, model_version, ...). */
export async function callJson<T>(
  envelopeSchema: z.ZodType<{ data: T | null; meta?: z.infer<typeof Meta>; error?: z.infer<typeof ErrorPayload> | null }>,
  request: () => Promise<unknown>,
): Promise<UnpackedResponse<T>> {
  const raw = await request();
  const parsed = envelopeSchema.safeParse(raw);
  if (!parsed.success) {
    throw new ApiError(
      `Invalid response shape: ${parsed.error.message}`,
      500,
      "schema_mismatch",
    );
  }
  if (parsed.data.error) {
    throw new ApiError(
      parsed.data.error.message,
      400,
      parsed.data.error.code,
      parsed.data.error.details,
    );
  }
  if (parsed.data.data === null || parsed.data.data === undefined) {
    throw new ApiError("Empty response", 204, "empty_response");
  }
  return { data: parsed.data.data, meta: parsed.data.meta ?? {} };
}
