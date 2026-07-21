import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MismatchBanner, isSymbolTimeframeMismatch } from "@/components/MismatchBanner";

describe("isSymbolTimeframeMismatch", () => {
  it("is false when both symbol and timeframe match", () => {
    expect(isSymbolTimeframeMismatch("MNQ1!", "5m", "MNQ1!", "5m")).toBe(false);
  });

  it("is true on a symbol mismatch", () => {
    expect(isSymbolTimeframeMismatch("MNQ1!", "5m", "ESU6", "5m")).toBe(true);
  });

  it("is true on a timeframe mismatch", () => {
    expect(isSymbolTimeframeMismatch("MNQ1!", "5m", "MNQ1!", "1m")).toBe(true);
  });
});

describe("MismatchBanner", () => {
  it("renders nothing when the live selection matches the frozen identity", () => {
    const { container } = render(
      <MismatchBanner frozenSymbol="MNQ1!" frozenTimeframe="5m" liveSymbol="MNQ1!" liveTimeframe="5m" />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("renders the exact required copy on a mismatch", () => {
    render(<MismatchBanner frozenSymbol="MNQ1!" frozenTimeframe="5m" liveSymbol="ESU6" liveTimeframe="1m" />);
    expect(screen.getByText("Frozen research baseline is available for MNQ1! / 5m.")).toBeInTheDocument();
    expect(screen.getByText(/Current live selection:/)).toBeInTheDocument();
    expect(screen.getByText("ESU6")).toBeInTheDocument();
    expect(screen.getByText("1m")).toBeInTheDocument();
  });
});
