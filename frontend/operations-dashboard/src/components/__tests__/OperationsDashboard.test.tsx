import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
import { OperationsDashboard } from "@/components/OperationsDashboard";
import * as polling from "@/lib/polling";

const snapshot = {
  health: { ok: true, service: "trader-now-read-only" },
  readiness: { ok: true, service: "trader-now-read-only" },
  operations: {
    service: { status: "healthy", started_at: "2026-07-24T10:00:00Z", uptime_seconds: 3660 },
    build: {
      commit: "1f10332a792c", release_tag: "v1.0.0", build_timestamp: "2026-07-24T10:00:00Z",
      response_schema_version: "trader_now_response.v2", domain_schema_version: "trader_now.v2",
    },
    database: { ready: true, transaction_read_only: true, pool_status: "open", latest_probe_duration_ms: 2.3 },
    requests: { last_success_at: "2026-07-24T10:10:00Z", last_response_duration_ms: 441.2 },
  },
  latest: {
    evaluated_at: "2026-07-24T10:10:00Z",
    identity: { product: "MNQ", strategy_id: "displacement_volume_context", strategy_version: "v1" },
    availability: {},
    market: {
      availability: { status: "available", reason_codes: [] },
      economic_instrument: { symbol: "MNQ" },
      market_data_series: { provider: "tradingview", symbol: "MNQ1!", series_type: "continuous" },
      latest_closed_at: "2026-07-24T10:05:00Z", bar_count: 288,
    },
    source_trust: { freshness: { status: "current", lateness_seconds: 5 } },
    rules: { facts: [{ fact_id: "volume_confirmation", value: true }] },
    interpretations: { interpretations: [{ setup_id: "setup-a", direction: "neutral", reason_codes: ["observed"] }] },
    strategy: { decisions: [{ strategy_id: "displacement_volume_context", strategy_version: "v1", reason_codes: ["observed"], confidence: 0.75 }] },
  },
  correlationId: "correlation-id",
};

describe("operations dashboard", () => {
  it("renders the healthy and no-trading-advice operational state", () => {
    vi.spyOn(polling, "useOperationsPolling").mockReturnValue({
      data: snapshot, lastRefresh: new Date("2026-07-24T10:10:00Z"), state: "polling", stale: false,
    });
    render(<OperationsDashboard />);
    expect(screen.getByText("TraderNow Operations")).toBeInTheDocument();
    expect(screen.getByText("MNQ1!")).toBeInTheDocument();
    expect(screen.getByText("volume_confirmation")).toBeInTheDocument();
    expect(screen.queryByText(/buy|sell/i)).not.toBeInTheDocument();
  });

  it("marks retained data stale and degraded", () => {
    vi.spyOn(polling, "useOperationsPolling").mockReturnValue({
      data: {
        ...snapshot,
        readiness: { ok: false, code: "database_unavailable" },
        operations: {
          ...snapshot.operations,
          service: { ...snapshot.operations.service, status: "degraded" },
          database: { ...snapshot.operations.database, ready: false, transaction_read_only: false },
        },
      },
      lastRefresh: new Date("2026-07-24T10:10:00Z"), state: "backoff", stale: true,
    });
    render(<OperationsDashboard />);
    expect(screen.getAllByText("Stale").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Degraded").length).toBeGreaterThan(0);
  });

  it("renders no-data truthfully", () => {
    vi.spyOn(polling, "useOperationsPolling").mockReturnValue({
      data: {
        ...snapshot,
        latest: {
          ...snapshot.latest,
          market: {
            ...snapshot.latest.market,
            availability: { status: "no_data", reason_codes: ["market_history_unavailable"] },
            latest_closed_at: null,
            bar_count: 0,
          },
          source_trust: null,
          strategy: { decisions: [] },
          interpretations: { interpretations: [] },
          rules: { facts: [] },
        },
      },
      lastRefresh: new Date(), state: "polling", stale: false,
    });
    render(<OperationsDashboard />);
    expect(screen.getByText("no_data")).toBeInTheDocument();
    expect(screen.getByText("0")).toBeInTheDocument();
    expect(screen.getAllByText("Unavailable").length).toBeGreaterThan(0);
  });
});
