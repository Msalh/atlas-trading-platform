import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SectionLoading } from "@/components/ResearchOps/SectionLoading";

describe("SectionLoading", () => {
  it("renders the given title and a Loading… message", () => {
    render(<SectionLoading title="Snapshot ID" />);
    expect(screen.getByText("Snapshot ID")).toBeInTheDocument();
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });
});
