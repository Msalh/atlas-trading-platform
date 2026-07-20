import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { EpisodeDurationStrip } from "@/components/EpisodeDurationStrip";

const distribution = { count: 5270, max: 10, mean: 1.48, median: 1, p75: 2, p90: 3, p95: 4 };

describe("EpisodeDurationStrip", () => {
  it("always shows the not-a-prediction caption", () => {
    render(<EpisodeDurationStrip distribution={distribution} liveDurationBars={5} />);
    expect(screen.getByText(/not a prediction of remaining duration/)).toBeInTheDocument();
  });

  it("shows the live duration marker only when a live duration is provided", () => {
    const { rerender } = render(<EpisodeDurationStrip distribution={distribution} liveDurationBars={5} />);
    expect(screen.getByTestId("live-duration-marker")).toBeInTheDocument();

    rerender(<EpisodeDurationStrip distribution={distribution} liveDurationBars={null} />);
    expect(screen.queryByTestId("live-duration-marker")).not.toBeInTheDocument();
  });

  it("renders percentile ticks", () => {
    render(<EpisodeDurationStrip distribution={distribution} liveDurationBars={null} />);
    expect(screen.getByTestId("tick-median")).toBeInTheDocument();
    expect(screen.getByTestId("tick-p75")).toBeInTheDocument();
    expect(screen.getByTestId("tick-p90")).toBeInTheDocument();
    expect(screen.getByTestId("tick-p95")).toBeInTheDocument();
  });

  it("clamps a live duration beyond the historical max to 100% rather than overflowing the axis", () => {
    render(<EpisodeDurationStrip distribution={distribution} liveDurationBars={50} />);
    const marker = screen.getByTestId("live-duration-marker");
    expect(marker.style.left).toBe("100%");
  });
});
