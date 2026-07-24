import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchRisk, RiskResponse } from "@/lib/riskApi";

function mockFetchOnce(body: unknown, status = 200) {
  global.fetch = vi.fn(async () => new Response(JSON.stringify(body), { status })) as unknown as typeof fetch;
}

const FLAT_RISK: RiskResponse = {
  account_configured: true,
  starting_balance: 50000,
  current_balance: 50696,
  high_water_mark: 50696,
  daily_loss_limit: 1000,
  daily_realized_pnl: 0,
  daily_loss_used: 0,
  daily_loss_remaining: 1000,
  daily_loss_limit_breached: false,
  trailing_drawdown_limit: 2000,
  trailing_stop_balance: 48696,
  remaining_drawdown: 2000,
  trailing_drawdown_breached: false,
  max_contracts: 5,
  point_value: 2,
  open_position: null,
  kill_switch: { should_trigger: false, reasons: [], enforced: false },
};

describe("fetchRisk", () => {
  const originalFetch = global.fetch;
  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("calls the same-origin proxy, not the backend directly", async () => {
    mockFetchOnce(FLAT_RISK);
    await fetchRisk();
    expect(global.fetch).toHaveBeenCalledWith("/api/proxy/risk", { cache: "no-store" });
  });

  it("parses a flat (no open position) risk snapshot", async () => {
    mockFetchOnce(FLAT_RISK);
    const result = await fetchRisk();
    expect(result.open_position).toBeNull();
    expect(result.kill_switch.should_trigger).toBe(false);
  });

  it("parses a risk snapshot with an open position and a triggered kill switch", async () => {
    mockFetchOnce({
      ...FLAT_RISK,
      daily_loss_limit_breached: true,
      kill_switch: { should_trigger: true, reasons: ["daily_loss_limit_breached"], enforced: false },
      open_position: {
        correlation_id: "abc123",
        direction: "long",
        quantity: 2,
        entry_price: 29600,
        sl: 29580,
        tp: 29650,
        current_price: 29610,
        unrealized_pnl: 40,
        risk_points: 20,
        reward_points: 50,
        risk_dollars: 80,
        reward_dollars: 200,
        exposure_contracts: 2,
        exposure_pct_of_max: 40,
        exceeds_max_contracts: false,
      },
    });
    const result = await fetchRisk();
    expect(result.kill_switch.should_trigger).toBe(true);
    expect(result.open_position?.direction).toBe("long");
    expect(result.open_position?.risk_dollars).toBe(80);
  });

  it("throws not_found on a 404", async () => {
    mockFetchOnce({ ok: false, error: "not found" }, 404);
    await expect(fetchRisk()).rejects.toMatchObject({ kind: "not_found" });
  });

  it("rejects a response with a malformed kill_switch", async () => {
    mockFetchOnce({ ...FLAT_RISK, kill_switch: { should_trigger: "yes" } });
    await expect(fetchRisk()).rejects.toMatchObject({ kind: "invalid_response" });
  });

  it("rejects a response with an invalid open_position.direction", async () => {
    mockFetchOnce({
      ...FLAT_RISK,
      open_position: {
        correlation_id: "abc123",
        direction: "sideways",
        quantity: null,
        entry_price: null,
        sl: null,
        tp: null,
        current_price: null,
        unrealized_pnl: null,
        risk_points: null,
        reward_points: null,
        risk_dollars: null,
        reward_dollars: null,
        exposure_contracts: null,
        exposure_pct_of_max: null,
        exceeds_max_contracts: false,
      },
    });
    await expect(fetchRisk()).rejects.toMatchObject({ kind: "invalid_response" });
  });

  it("throws network_error when fetch itself throws", async () => {
    global.fetch = vi.fn(async () => {
      throw new TypeError("fetch failed");
    }) as unknown as typeof fetch;
    await expect(fetchRisk()).rejects.toMatchObject({ kind: "network_error" });
  });
});
