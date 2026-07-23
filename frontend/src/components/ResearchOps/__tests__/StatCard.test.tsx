import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatCard } from "@/components/ResearchOps/StatCard";

describe("StatCard", () => {
  it("renders label, value, and detail", () => {
    render(<StatCard label="Promotions" value="12" detail="total decisions recorded" />);
    expect(screen.getByText("Promotions")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("total decisions recorded")).toBeInTheDocument();
  });

  it("renders the empty message instead of value/detail when `empty` is set", () => {
    render(<StatCard label="Latest Snapshot" value="snap_1" detail="should not render" empty="No snapshot recorded yet." />);
    expect(screen.getByText("No snapshot recorded yet.")).toBeInTheDocument();
    expect(screen.queryByText("snap_1")).not.toBeInTheDocument();
    expect(screen.queryByText("should not render")).not.toBeInTheDocument();
  });

  it("omits detail when not provided", () => {
    render(<StatCard label="Promotions" value="0" />);
    expect(screen.getByText("0")).toBeInTheDocument();
  });
});
