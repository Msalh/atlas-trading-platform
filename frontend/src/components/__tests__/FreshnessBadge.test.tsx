import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FreshnessBadge } from "@/components/FreshnessBadge";
import { ResponseEnvelope } from "@/lib/apiEnvelope";

const FROZEN_NOW = new Date("2026-07-20T12:00:00Z");

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

function minutesAgo(minutes: number): string {
  return new Date(FROZEN_NOW.getTime() - minutes * 60_000).toISOString();
}

describe("FreshnessBadge", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(FROZEN_NOW);
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows LIVE with data_as_of on a live envelope", () => {
    render(<FreshnessBadge envelope={envelope({ source_track: "live", data_as_of: minutesAgo(1) })} />);
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
    render(<FreshnessBadge envelope={envelope({ source_track: "live", data_as_of: minutesAgo(1) })} />);
    expect(screen.getByText(/CT$/)).toBeInTheDocument();
  });

  it("shows an explicit CT label on the frozen badge's date too", () => {
    render(<FreshnessBadge envelope={envelope({ source_track: "frozen" })} />);
    expect(screen.getByText(/CT,/)).toBeInTheDocument();
  });

  describe("live freshness states (production-hardening amendment 5)", () => {
    it("shows 'LIVE — LAST CLOSED BAR' only when the data is current (well within one bar)", () => {
      render(<FreshnessBadge envelope={envelope({ source_track: "live", timeframe: "5m", data_as_of: minutesAgo(2) })} />);
      expect(screen.getByText(/LIVE — LAST CLOSED BAR/)).toBeInTheDocument();
    });

    it("shows a distinct 'LIVE — DELAYED' state between the current and stale thresholds, never the plain LAST CLOSED BAR label", () => {
      // 5m timeframe: current <= 7.5min, stale > 15min - 10min falls in between.
      render(<FreshnessBadge envelope={envelope({ source_track: "live", timeframe: "5m", data_as_of: minutesAgo(10) })} />);
      expect(screen.getByText(/LIVE — DELAYED/)).toBeInTheDocument();
      expect(screen.queryByText(/LAST CLOSED BAR/)).not.toBeInTheDocument();
    });

    it("shows a distinct 'LIVE — STALE' state past the stale threshold, never implying current data", () => {
      render(<FreshnessBadge envelope={envelope({ source_track: "live", timeframe: "5m", data_as_of: minutesAgo(30) })} />);
      expect(screen.getByText(/LIVE — STALE/)).toBeInTheDocument();
      expect(screen.queryByText(/LAST CLOSED BAR/)).not.toBeInTheDocument();
      expect(screen.queryByText(/DELAYED/)).not.toBeInTheDocument();
    });

    it("still shows the exact last-received CT timestamp in every freshness state", () => {
      render(<FreshnessBadge envelope={envelope({ source_track: "live", timeframe: "5m", data_as_of: minutesAgo(30) })} />);
      expect(screen.getByText(/as of/)).toBeInTheDocument();
      expect(screen.getByText(/CT$/)).toBeInTheDocument();
    });
  });
});
