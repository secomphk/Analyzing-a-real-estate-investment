import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useScenarioA } from "@/hooks/useProjects";
import { makeWrapper } from "@/test/test-utils";

describe("useScenarioA", () => {
  it("fetches and unwraps the envelope", async () => {
    const { result } = renderHook(
      () => useScenarioA({ project_id: 1 }),
      { wrapper: makeWrapper() },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const data = result.current.data?.data;
    expect(data?.project_id).toBe(1);
    expect(data?.zones[0].admin_name).toBe("운양동");
    expect(result.current.data?.meta.model_version).toMatch(/scenario_a/);
  });

  it("stays disabled when project_id is missing", () => {
    const { result } = renderHook(() => useScenarioA(null), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });
});
