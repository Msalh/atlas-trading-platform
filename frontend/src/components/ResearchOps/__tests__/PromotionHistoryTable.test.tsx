import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PromotionHistoryTable } from "@/components/ResearchOps/PromotionHistoryTable";

describe("PromotionHistoryTable", () => {
  it("renders one row per record with hypothesis, realization, decision, decided timestamp, reason, snapshot reference", () => {
    render(
      <PromotionHistoryTable
        rows={[
          { promotionId: "p1", hypothesisId: "h1", realizationId: "r1", decision: "approved", decidedAt: "2026-07-23T14:00:00Z", rationale: "strong out-of-sample edge", evidenceSnapshotRef: "snap_1" },
          { promotionId: "p2", hypothesisId: "h2", realizationId: null, decision: "declined", decidedAt: "2026-07-23T14:00:00Z", rationale: "insufficient sample size", evidenceSnapshotRef: "snap_1" },
        ]}
      />,
    );
    expect(screen.getByText("h1")).toBeInTheDocument();
    expect(screen.getByText("r1")).toBeInTheDocument();
    expect(screen.getByText("Approved")).toBeInTheDocument();
    expect(screen.getByText("strong out-of-sample edge")).toBeInTheDocument();
    expect(screen.getByText("h2")).toBeInTheDocument();
    // Sprint 10 Slice E.1: History renders the immutable decision as plain
    // "Declined" - unlike the Queue's "Previously Declined" - because a
    // PromotionRecord already carries a final, made decision here, not a
    // reconsideration-in-progress. No PromotionStatusBadge `label` override
    // is passed by this table.
    expect(screen.getByText("Declined")).toBeInTheDocument();
    expect(screen.queryByText("Previously Declined")).not.toBeInTheDocument();
    expect(screen.getByText("insufficient sample size")).toBeInTheDocument();
    expect(screen.getAllByText("snap_1")).toHaveLength(2);
  });

  it("omits the realization sub-line for a record with no realization_id", () => {
    render(<PromotionHistoryTable rows={[{ promotionId: "p1", hypothesisId: "h1", realizationId: null, decision: "deferred", decidedAt: "2026-07-23T14:00:00Z", rationale: "needs more data", evidenceSnapshotRef: "snap_1" }]} />);
    expect(screen.queryByText("null")).not.toBeInTheDocument();
  });

  it("renders no rows for an empty array without crashing", () => {
    const { container } = render(<PromotionHistoryTable rows={[]} />);
    expect(container.querySelectorAll("tbody tr")).toHaveLength(0);
  });

  it("renders column headers exactly - Hypothesis, Decision, Decided, Reason, Snapshot Reference", () => {
    render(<PromotionHistoryTable rows={[]} />);
    for (const header of ["Hypothesis", "Decision", "Decided", "Reason", "Snapshot Reference"]) {
      expect(screen.getByText(header)).toBeInTheDocument();
    }
  });
});
