import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchStatsToday, StatsTodayResponse } from "@/lib/statsApi";

function mockFetchOnce(body: unknown, status = 200) {
  global.fetch = vi.fn(async () => new Response(JSON.stringify(body), { status })) as unknown as typeof fetch;
}

const FLAT_STATS: StatsTodayResponse = {
  date_utc: "2026-07-24",
  trades_entered_today: 0,
  trades_closed_today: 0,
  wins_today: 0,
  losses_today: 0,
  realized_pnl_today: 0,
  pmt_forward_failures_today: 0,
  open_position: { correlation_id: null, risk_points: null, reward_points: null },
};

describe("fetchStatsToday", () => {
  const originalFetch = global.fetch;
  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("calls the same-origin proxy, not the backend directly", async () => {
    mockFetchOnce(FLAT_STATS);
    await fetchStatsToday();
    expect(global.fetch).toHaveBeenCalledWith("/api/proxy/stats/today", { cache: "no-store" });
  });

  it("parses a quiet (no trades today) response", async () => {
    mockFetchOnce(FLAT_STATS);
    const result = await fetchStatsToday();
    expect(result.trades_entered_today).toBe(0);
    expect(result.open_position.correlation_id).toBeNull();
  });

  it("parses a response with an open position and forward failures", async () => {
    mockFetchOnce({
      ...FLAT_STATS,
      trades_entered_today: 3,
      pmt_forward_failures_today: 1,
      open_position: { correlation_id: "abc123", risk_points: 20, reward_points: 50 },
    });
    const result = await fetchStatsToday();
    expect(result.pmt_forward_failures_today).toBe(1);
    expect(result.open_position.correlation_id).toBe("abc123");
  });

  it("rejects a response missing open_position", async () => {
    mockFetchOnce({
      date_utc: "2026-07-24",
      trades_entered_today: 0,
      trades_closed_today: 0,
      wins_today: 0,
      losses_today: 0,
      realized_pnl_today: 0,
      pmt_forward_failures_today: 0,
    });
    await expect(fetchStatsToday()).rejects.toMatchObject({ kind: "invalid_response" });
  });

  it("throws network_error when fetch itself throws", async () => {
    global.fetch = vi.fn(async () => {
      throw new TypeError("fetch failed");
    }) as unknown as typeof fetch;
    await expect(fetchStatsToday()).rejects.toMatchObject({ kind: "network_error" });
  });
});
