import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CertificationTable } from "@/components/DatasetHealthPanels/CertificationTable";
import { CertificationSummary } from "@/lib/researchApi";

function summary(overrides: Partial<CertificationSummary> = {}): CertificationSummary {
  return {
    checks_run: 3,
    pass_count: 2,
    warning_count: 1,
    fail_count: 0,
    verdict: "certified_with_warnings",
    checks: [
      { section: "0. Ingestion", check: "Row parsing", verdict: "PASS", detail: "all rows parsed" },
      { section: "0. Ingestion", check: "Duplicate timestamps", verdict: "PASS", detail: "no duplicates" },
      { section: "1. Continuity", check: "Gap detection", verdict: "WARNING", detail: "2 gaps found" },
    ],
    ...overrides,
  };
}

describe("CertificationTable", () => {
  it("shows the overall verdict with underscores replaced by spaces", () => {
    render(<CertificationTable certification={summary()} />);
    expect(screen.getByText("certified with warnings")).toBeInTheDocument();
  });

  it("shows the checks_run/pass/warning/fail summary line", () => {
    render(<CertificationTable certification={summary()} />);
    expect(screen.getByText(/3 checks/)).toBeInTheDocument();
    expect(screen.getByText(/2 pass/)).toBeInTheDocument();
    expect(screen.getByText(/1 warning/)).toBeInTheDocument();
    expect(screen.getByText(/0 fail/)).toBeInTheDocument();
  });

  it("groups checks by section", () => {
    render(<CertificationTable certification={summary()} />);
    expect(screen.getAllByText("0. Ingestion").length).toBeGreaterThan(0);
    expect(screen.getAllByText("1. Continuity").length).toBeGreaterThan(0);
    expect(screen.getByText("Gap detection")).toBeInTheDocument();
  });

  it("renders a rejected verdict distinctly", () => {
    render(
      <CertificationTable
        certification={summary({
          verdict: "rejected",
          fail_count: 1,
          checks: [{ section: "0. Ingestion", check: "Row parsing", verdict: "FAIL", detail: "bad row" }],
        })}
      />,
    );
    expect(screen.getByText("rejected")).toBeInTheDocument();
    expect(screen.getByText("FAIL")).toBeInTheDocument();
  });
});
