import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ModeToggle } from "@/components/scenarios/c/ModeToggle";

describe("ModeToggle", () => {
  it("renders the active tab and fires onChange when another is clicked", async () => {
    const onChange = vi.fn();
    render(<ModeToggle mode="impact" onChange={onChange} />);
    expect(screen.getByRole("tab", { name: /매장 분석/i })).toHaveAttribute("aria-selected", "true");

    await userEvent.click(screen.getByRole("tab", { name: /후보지 발굴/i }));
    expect(onChange).toHaveBeenCalledWith("candidates");
  });
});
