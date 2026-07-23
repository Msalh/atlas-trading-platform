import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { NextStepLink } from "@/components/ResearchOps/NextStepLink";

describe("NextStepLink", () => {
  it("renders a link to the given href with the label in 'Next: <label> →' form", () => {
    render(<NextStepLink href="/research-ops/leaderboard" label="Leaderboard" />);
    const link = screen.getByRole("link", { name: "Next: Leaderboard →" });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute("href", "/research-ops/leaderboard");
  });
});
