import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { LeaderboardTable } from "@/components/ResearchOps/LeaderboardTable";

describe("LeaderboardTable", () => {
  it("renders one row per entry with rank, hypothesis, score, validation, and status", () => {
    render(
      <LeaderboardTable
        rows={[
          { rank: 1, hypothesisId: "h1", realizationId: "r1", score: 1.0, validationId: "v1", status: "approved" },
          { rank: 2, hypothesisId: "h2", realizationId: null, score: 0.9, validationId: "v2", status: "pending" },
        ]}
      />,
    );
    expect(screen.getByText("h1")).toBeInTheDocument();
    expect(screen.getByText("r1")).toBeInTheDocument();
    expect(screen.getByText("v1")).toBeInTheDocument();
    expect(screen.getByText("Approved")).toBeInTheDocument();
    expect(screen.getByText("h2")).toBeInTheDocument();
    expect(screen.getByText("Pending Review")).toBeInTheDocument();
  });

  it("omits the realization sub-line for a decision-free entry", () => {
    render(<LeaderboardTable rows={[{ rank: 1, hypothesisId: "h1", realizationId: null, score: 1.0, validationId: "v1", status: "pending" }]} />);
    expect(screen.queryByText("null")).not.toBeInTheDocument();
  });

  it("renders an em dash for a missing validation id", () => {
    render(<LeaderboardTable rows={[{ rank: 1, hypothesisId: "h1", realizationId: null, score: 1.0, validationId: null, status: "pending" }]} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("renders no rows for an empty array without crashing", () => {
    const { container } = render(<LeaderboardTable rows={[]} />);
    expect(container.querySelectorAll("tbody tr")).toHaveLength(0);
  });

  it("renders column headers exactly - Rank, Hypothesis, Score, Validation, Status", () => {
    render(<LeaderboardTable rows={[]} />);
    for (const header of ["Rank", "Hypothesis", "Score", "Validation", "Status"]) {
      expect(screen.getByText(header)).toBeInTheDocument();
    }
  });
});
