import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PromotionQueueTable } from "@/components/ResearchOps/PromotionQueueTable";

describe("PromotionQueueTable", () => {
  it("renders one row per candidate with hypothesis, realization, validation, score, status, snapshot", () => {
    render(
      <PromotionQueueTable
        rows={[
          { hypothesisId: "h1", realizationId: "r1", validationId: "v1", score: 0.9, status: "pending", snapshotId: "snap_1" },
          { hypothesisId: "h2", realizationId: null, validationId: "v2", score: 0.8, status: "deferred", snapshotId: "snap_1" },
        ]}
      />,
    );
    expect(screen.getByText("h1")).toBeInTheDocument();
    expect(screen.getByText("r1")).toBeInTheDocument();
    expect(screen.getByText("v1")).toBeInTheDocument();
    expect(screen.getByText("Pending Review")).toBeInTheDocument();
    expect(screen.getByText("h2")).toBeInTheDocument();
    expect(screen.getByText("Deferred")).toBeInTheDocument();
    expect(screen.getAllByText("snap_1")).toHaveLength(2);
  });

  it("renders a declined candidate as Previously Declined, not Declined - Slice E.1: it remains eligible for reconsideration", () => {
    render(<PromotionQueueTable rows={[{ hypothesisId: "h1", realizationId: "r1", validationId: "v1", score: 0.9, status: "declined", snapshotId: "snap_1" }]} />);
    expect(screen.getByText("Previously Declined")).toBeInTheDocument();
    expect(screen.queryByText("Declined")).not.toBeInTheDocument();
  });

  it("omits the realization sub-line for a candidate with no realization_id", () => {
    render(<PromotionQueueTable rows={[{ hypothesisId: "h1", realizationId: null, validationId: "v1", score: 1.0, status: "pending", snapshotId: "snap_1" }]} />);
    expect(screen.queryByText("null")).not.toBeInTheDocument();
  });

  it("renders an em dash for a missing validation id", () => {
    render(<PromotionQueueTable rows={[{ hypothesisId: "h1", realizationId: null, validationId: null, score: 1.0, status: "pending", snapshotId: "snap_1" }]} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("renders no rows for an empty array without crashing", () => {
    const { container } = render(<PromotionQueueTable rows={[]} />);
    expect(container.querySelectorAll("tbody tr")).toHaveLength(0);
  });

  it("renders column headers exactly - Hypothesis, Validation, Score, Status, Snapshot - and no Timestamp column (Slice E.1)", () => {
    render(<PromotionQueueTable rows={[]} />);
    for (const header of ["Hypothesis", "Validation", "Score", "Status", "Snapshot"]) {
      expect(screen.getByText(header)).toBeInTheDocument();
    }
    expect(screen.queryByText("Timestamp")).not.toBeInTheDocument();
  });
});
