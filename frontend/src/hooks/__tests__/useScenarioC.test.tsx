import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useDTCandidates, useLandSuitability, useStoreImpact } from "@/hooks/useScenarioC";
import { makeWrapper } from "@/test/test-utils";

describe("useStoreImpact", () => {
  it("returns the band matrix", async () => {
    const { result } = renderHook(
      () => useStoreImpact({ store_id: 11 }),
      { wrapper: makeWrapper() },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const data = result.current.data?.data;
    expect(data?.bands.length).toBeGreaterThan(0);
    expect(data?.bands[0].band_m).toBe(500);
  });
});

describe("useLandSuitability", () => {
  it("returns DT score with rationales", async () => {
    const { result } = renderHook(
      () => useLandSuitability({ pnu: "4128010500100010000", target: "DT" }),
      { wrapper: makeWrapper() },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const data = result.current.data?.data;
    expect(data?.target).toBe("DT");
    expect(data?.score_100).toBe(78);
    expect(data?.rationales).toHaveLength(2);
  });
});

describe("useDTCandidates", () => {
  it("returns ranked candidates", async () => {
    const { result } = renderHook(
      () => useDTCandidates({ region_code: "41280", target: "DT", top_n: 5 }),
      { wrapper: makeWrapper() },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const data = result.current.data?.data;
    expect(data?.candidates.length).toBeGreaterThan(0);
    expect(data?.candidates[0].suitability.score_100).toBeGreaterThan(0);
  });
});
