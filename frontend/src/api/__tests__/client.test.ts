import { describe, expect, it } from "vitest";
import { z } from "zod";

import { ApiError, callJson } from "@/api/client";
import { envelope } from "@/api/schemas";

const TestSchema = envelope(z.object({ ok: z.boolean() }));

describe("callJson", () => {
  it("unwraps a successful envelope", async () => {
    const out = await callJson(TestSchema, () =>
      Promise.resolve({ data: { ok: true }, meta: {}, error: null }),
    );
    expect(out.data.ok).toBe(true);
  });

  it("throws ApiError when error is populated", async () => {
    await expect(
      callJson(TestSchema, () =>
        Promise.resolve({ data: null, meta: {}, error: { code: "x", message: "bad" } }),
      ),
    ).rejects.toBeInstanceOf(ApiError);
  });

  it("throws when the shape doesn't match the schema", async () => {
    await expect(
      callJson(TestSchema, () =>
        Promise.resolve({ data: { ok: "not a bool" }, meta: {}, error: null } as never),
      ),
    ).rejects.toMatchObject({ code: "schema_mismatch" });
  });

  it("throws when data is null and there's no error", async () => {
    await expect(
      callJson(TestSchema, () =>
        Promise.resolve({ data: null, meta: {}, error: null }),
      ),
    ).rejects.toMatchObject({ code: "empty_response" });
  });
});
