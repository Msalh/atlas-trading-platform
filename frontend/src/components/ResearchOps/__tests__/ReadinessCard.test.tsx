import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ReadinessCard } from "@/components/ResearchOps/ReadinessCard";

describe("ReadinessCard", () => {
  it("renders the title and status label", () => {
    render(<ReadinessCard title="Research Status" status="ok" statusLabel="Healthy" />);
    expect(screen.getByText("Research Status")).toBeInTheDocument();
    expect(screen.getByText("Healthy")).toBeInTheDocument();
  });

  it("renders detail text when provided", () => {
    render(<ReadinessCard title="Ledger Readiness" status="degraded" statusLabel="Degraded" detail="research_ledger_not_configured" />);
    expect(screen.getByText("research_ledger_not_configured")).toBeInTheDocument();
  });

  it("omits detail text when not provided", () => {
    const { container } = render(<ReadinessCard title="Research Status" status="ok" statusLabel="Healthy" />);
    expect(container.querySelectorAll("p")).toHaveLength(0);
  });

  it("renders each check with its own label and detail", () => {
    render(
      <ReadinessCard
        title="Ledger Readiness"
        status="degraded"
        statusLabel="Degraded"
        checks={[
          { label: "Configuration valid", ok: false, detail: "RESEARCH_LEDGER_DIR is not set" },
          { label: "Ledger directory", ok: true },
        ]}
      />,
    );
    expect(screen.getByText("Configuration valid")).toBeInTheDocument();
    expect(screen.getByText("RESEARCH_LEDGER_DIR is not set")).toBeInTheDocument();
    expect(screen.getByText("Ledger directory")).toBeInTheDocument();
  });

  it("omits the checks list entirely when none are given", () => {
    const { container } = render(<ReadinessCard title="Research Status" status="ok" statusLabel="Healthy" />);
    expect(container.querySelector("ul")).toBeNull();
  });
});
