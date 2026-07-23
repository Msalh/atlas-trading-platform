import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PromotionStatusBadge } from "@/components/ResearchOps/PromotionStatusBadge";

describe("PromotionStatusBadge", () => {
  it("renders Pending Review for a candidate with no decision yet", () => {
    render(<PromotionStatusBadge status="pending" />);
    expect(screen.getByText("Pending Review")).toBeInTheDocument();
  });

  it("renders Approved", () => {
    render(<PromotionStatusBadge status="approved" />);
    expect(screen.getByText("Approved")).toBeInTheDocument();
  });

  it("renders Declined", () => {
    render(<PromotionStatusBadge status="declined" />);
    expect(screen.getByText("Declined")).toBeInTheDocument();
  });

  it("renders Deferred", () => {
    render(<PromotionStatusBadge status="deferred" />);
    expect(screen.getByText("Deferred")).toBeInTheDocument();
  });

  it("renders the label override in place of the default status text when given (Slice E.1)", () => {
    render(<PromotionStatusBadge status="declined" label="Previously Declined" />);
    expect(screen.getByText("Previously Declined")).toBeInTheDocument();
    expect(screen.queryByText("Declined")).not.toBeInTheDocument();
  });

  it("falls back to the default status text when no label override is given", () => {
    render(<PromotionStatusBadge status="declined" />);
    expect(screen.getByText("Declined")).toBeInTheDocument();
  });
});
