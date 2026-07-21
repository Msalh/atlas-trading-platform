import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FreshnessBadge } from "@/components/FreshnessBadge";
import { ResponseEnvelope } from "@/lib/apiEnvelope";

function envelope(overrides: Partial<ResponseEnvelope>): ResponseEnvelope {
  return {
    schema_version: "1.0",
    source_track: "live",
    symbol: "MNQU6",
    timeframe: "5m",
    generated_at: "2026-07-20T12:00:00Z",
    data_as_of: "2026-07-20T11:55:00Z",
    code_version: "abc1234def",
    warnings: [],
    ...overrides,
  };
}

describe("FreshnessBadge", () => {
  it("shows LIVE with data_as_of on a live envelope", () => {
    render(<FreshnessBadge envelope={envelope({ source_track: "live" })} />);
    expect(screen.getByText(/LIVE/)).toBeInTheDocument();
  });

  it("shows source_computation_version, never snapshot_exporter_version, on a frozen envelope", () => {
    render(
      <FreshnessBadge
        envelope={envelope({
          source_track: "frozen",
          code_version: "a907325fbb357097fb0e8e064d46772e2b719964",
        })}
      />,
    );
    expect(screen.getByText(/FROZEN BASELINE/)).toBeInTheDocument();
    expect(screen.getByText(/a907325/)).toBeInTheDocument();
  });

  it("renders 'unknown' rather than crashing when code_version is null", () => {
    render(<FreshnessBadge envelope={envelope({ source_track: "frozen", code_version: null })} />);
    expect(screen.getByText(/unknown/)).toBeInTheDocument();
  });

  it("never renders the word LIVE on a frozen envelope", () => {
    render(<FreshnessBadge envelope={envelope({ source_track: "frozen" })} />);
    expect(screen.queryByText(/^LIVE/)).not.toBeInTheDocument();
  });

  it("shows an explicit CT label on both the live and frozen badge, never the viewer's local time unlabeled", () => {
    render(<FreshnessBadge envelope={envelope({ source_track: "live" })} />);
    expect(screen.getByText(/CT$/)).toBeInTheDocument();
  });

  it("shows an explicit CT label on the frozen badge's date too", () => {
    render(<FreshnessBadge envelope={envelope({ source_track: "frozen" })} />);
    expect(screen.getByText(/CT,/)).toBeInTheDocument();
  });
});
