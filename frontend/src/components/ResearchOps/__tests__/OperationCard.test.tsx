import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { OperationCard } from "@/components/ResearchOps/OperationCard";

describe("OperationCard", () => {
  it("renders name, description, availability, prerequisites, and current state", () => {
    render(
      <OperationCard
        name="Research Run"
        description="Executes the research pipeline end-to-end."
        availability="available"
        prerequisites={["Research Ledger must be ready"]}
        state="Last observed output: snapshot snap_1."
      />,
    );
    expect(screen.getByText("Research Run")).toBeInTheDocument();
    expect(screen.getByText("Executes the research pipeline end-to-end.")).toBeInTheDocument();
    expect(screen.getByText("Available")).toBeInTheDocument();
    expect(screen.getByText("Research Ledger must be ready")).toBeInTheDocument();
    expect(screen.getByText("Last observed output: snapshot snap_1.")).toBeInTheDocument();
  });

  it("renders Unavailable with a detail reason", () => {
    render(
      <OperationCard
        name="Research Run"
        description="Executes the research pipeline end-to-end."
        availability="unavailable"
        availabilityDetail="Research Ledger is not ready."
        prerequisites={["Research Ledger must be ready"]}
        state="Checking…"
      />,
    );
    expect(screen.getByText("Unavailable")).toBeInTheDocument();
    expect(screen.getByText("Research Ledger is not ready.")).toBeInTheDocument();
  });

  it("renders Not Implemented for a declared-but-unbuilt operation", () => {
    render(
      <OperationCard
        name="Replay"
        description="A declared run mode. Not yet built."
        availability="not_implemented"
        availabilityDetail="Declared as a run mode, but not yet implemented."
        prerequisites={[]}
        state="No prior executions - not yet implemented."
      />,
    );
    expect(screen.getByText("Not Implemented")).toBeInTheDocument();
    expect(screen.getByText("None")).toBeInTheDocument(); // empty prerequisites list
  });

  it("renders Not a Standalone Operation for an embedded pipeline stage", () => {
    render(
      <OperationCard
        name="Validation"
        description="Runs automatically inside a Research Run."
        availability="not_standalone"
        prerequisites={["Evidence must already exist"]}
        state="0 of 1 entries carry a validation result."
      />,
    );
    expect(screen.getByText("Not a Standalone Operation")).toBeInTheDocument();
  });

  it("renders no action buttons of any kind - informational only", () => {
    render(
      <OperationCard
        name="Research Run"
        description="Executes the research pipeline end-to-end."
        availability="available"
        prerequisites={[]}
        state="Checking…"
      />,
    );
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
