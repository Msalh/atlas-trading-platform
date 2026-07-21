import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { KnownWarningsList } from "@/components/DatasetHealthPanels/KnownWarningsList";
import { KnownWarning } from "@/lib/researchApi";

function warning(overrides: Partial<KnownWarning> = {}): KnownWarning {
  return {
    id: "trend-1m-lookback-limit",
    severity: "warning",
    title: "trend_1m unreliable before 2025-07-20",
    detail: "A TradingView 1-minute-data lookback boundary, not a pipeline defect.",
    source_document: "docs/market_engine/re1-phase5-freeze.md",
    source_section: "Known limitations, item 1",
    ...overrides,
  };
}

describe("KnownWarningsList", () => {
  it("shows a fallback message when there are no warnings", () => {
    render(<KnownWarningsList warnings={[]} />);
    expect(screen.getByText(/No known warnings disclosed/)).toBeInTheDocument();
  });

  it("renders title, severity, and detail for each warning", () => {
    render(<KnownWarningsList warnings={[warning()]} />);
    expect(screen.getByText("trend_1m unreliable before 2025-07-20")).toBeInTheDocument();
    expect(screen.getByText("warning")).toBeInTheDocument();
    expect(screen.getByText(/lookback boundary/)).toBeInTheDocument();
  });

  it("always shows source_document and source_section directly, never hidden", () => {
    render(<KnownWarningsList warnings={[warning()]} />);
    expect(screen.getByText(/docs\/market_engine\/re1-phase5-freeze\.md/)).toBeInTheDocument();
    expect(screen.getByText(/Known limitations, item 1/)).toBeInTheDocument();
  });

  it("distinguishes a fail-severity warning from a warning-severity one", () => {
    render(<KnownWarningsList warnings={[warning({ id: "b", severity: "fail", title: "Certification rejected" })]} />);
    expect(screen.getByText("fail")).toBeInTheDocument();
  });
});
