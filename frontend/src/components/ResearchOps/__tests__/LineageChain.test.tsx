import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { LineageChain, LineageNode } from "@/components/ResearchOps/LineageChain";

describe("LineageChain", () => {
  it("renders one stage per node, in order, with each item's title and fields", () => {
    const nodes: LineageNode[] = [
      { label: "Hypothesis", items: [{ title: "h1", fields: [] }], emptyMessage: "No hypothesis." },
      {
        label: "Realization",
        items: [{ title: "r1", fields: [{ label: "Kind", value: "parameter_grid" }], badge: { label: "active", tone: "neutral" } }],
        emptyMessage: "No realization.",
      },
    ];
    render(<LineageChain nodes={nodes} />);
    expect(screen.getByText("Hypothesis")).toBeInTheDocument();
    expect(screen.getByText("h1")).toBeInTheDocument();
    expect(screen.getByText("Realization")).toBeInTheDocument();
    expect(screen.getByText("r1")).toBeInTheDocument();
    expect(screen.getByText("Kind")).toBeInTheDocument();
    expect(screen.getByText("parameter_grid")).toBeInTheDocument();
    expect(screen.getByText("active")).toBeInTheDocument();
  });

  it("renders a stage's own emptyMessage when it has zero items, without crashing", () => {
    const nodes: LineageNode[] = [{ label: "Promotion", items: [], emptyMessage: "No promotion decision recorded yet." }];
    render(<LineageChain nodes={nodes} />);
    expect(screen.getByText("No promotion decision recorded yet.")).toBeInTheDocument();
  });

  it("renders multiple items within a single stage (e.g. more than one experiment)", () => {
    const nodes: LineageNode[] = [
      {
        label: "Experiment",
        items: [
          { title: "exp1", fields: [], badge: { label: "Passed", tone: "ok" } },
          { title: "exp2", fields: [], badge: { label: "Failed", tone: "danger" } },
        ],
        emptyMessage: "No experiments.",
      },
    ];
    render(<LineageChain nodes={nodes} />);
    expect(screen.getByText("exp1")).toBeInTheDocument();
    expect(screen.getByText("exp2")).toBeInTheDocument();
    expect(screen.getByText("Passed")).toBeInTheDocument();
    expect(screen.getByText("Failed")).toBeInTheDocument();
  });

  it("renders an empty node list without crashing", () => {
    const { container } = render(<LineageChain nodes={[]} />);
    expect(container.querySelectorAll("li")).toHaveLength(0);
  });
});
