import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { EmptyPanel } from "@/components/ResearchOps/EmptyPanel";

describe("EmptyPanel", () => {
  it("renders the message in default tone", () => {
    const { container } = render(<EmptyPanel message="No candidates are currently awaiting review." />);
    expect(screen.getByText("No candidates are currently awaiting review.")).toBeInTheDocument();
    expect(container.firstChild).toHaveClass("text-muted");
    expect(container.firstChild).not.toHaveClass("text-danger");
  });

  it("renders the message in error tone", () => {
    const { container } = render(<EmptyPanel message="research ledger storage is degraded" tone="error" />);
    expect(screen.getByText("research ledger storage is degraded")).toBeInTheDocument();
    expect(container.firstChild).toHaveClass("text-danger");
  });
});
