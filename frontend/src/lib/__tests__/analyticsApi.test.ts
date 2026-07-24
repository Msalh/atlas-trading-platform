import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchAnalyticsSummary, fetchBreakdown, fetchEquityCurve } from "@/lib/analyticsApi";

function mockFetchOnce(body: unknown, status = 200) {
  global.fetch = vi.fn(async () => new Response(JSON.stringify(body), { status })) as unknown as typeof fetch;
}

const FLAT_SUMMARY = {
  total_trades: 0,
  wins: 0,
  losses: 0,
  win_rate_pct: 0,
  profit_factor: null,
  expectancy: 0,
  avg_win: null,
  avg_loss: null,
  avg_r: null,
  r_multiple_sample_size: 0,
};

describe("fetchAnalyticsSummary", () => {
  const originalFetch = global.fetch;
  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("calls the same-origin proxy, not the backend directly", async () => {
    mockFetchOnce(FLAT_SUMMARY);
    await fetchAnalyticsSummary();
    expect(global.fetch).toHaveBeenCalledWith("/api/proxy/analytics/summary", { cache: "no-store" });
  });

  it("parses a zero-trade summary", async () => {
    mockFetchOnce(FLAT_SUMMARY);
    const result = await fetchAnalyticsSummary();
    expect(result.total_trades).toBe(0);
    expect(result.profit_factor).toBeNull();
  });

  it("parses a populated summary", async () => {
    mockFetchOnce({
      ...FLAT_SUMMARY,
      total_trades: 10,
      wins: 7,
      losses: 3,
      win_rate_pct: 70,
      profit_factor: 2.5,
      expectancy: 150,
      avg_win: 300,
      avg_loss: -100,
      avg_r: 1.2,
      r_multiple_sample_size: 10,
    });
    const result = await fetchAnalyticsSummary();
    expect(result.win_rate_pct).toBe(70);
    expect(result.profit_factor).toBe(2.5);
  });

  it("rejects a response with a non-numeric win_rate_pct", async () => {
    mockFetchOnce({ ...FLAT_SUMMARY, win_rate_pct: "70%" });
    await expect(fetchAnalyticsSummary()).rejects.toMatchObject({ kind: "invalid_response" });
  });
});

describe("fetchEquityCurve", () => {
  const originalFetch = global.fetch;
  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("calls the same-origin proxy, not the backend directly", async () => {
    mockFetchOnce({ points: [], ending_equity: 50000, max_drawdown: 0, max_drawdown_pct: 0 });
    await fetchEquityCurve();
    expect(global.fetch).toHaveBeenCalledWith("/api/proxy/analytics/equity-curve", { cache: "no-store" });
  });

  it("parses an empty (no closed trades) curve", async () => {
    mockFetchOnce({ points: [], ending_equity: 50000, max_drawdown: 0, max_drawdown_pct: 0 });
    const result = await fetchEquityCurve();
    expect(result.points).toHaveLength(0);
  });

  it("parses a populated curve", async () => {
    mockFetchOnce({
      points: [
        { closed_at: "2026-07-14T11:30:00Z", equity: 50696, drawdown: 0 },
        { closed_at: "2026-07-20T09:00:00Z", equity: 50500, drawdown: 196 },
      ],
      ending_equity: 50500,
      max_drawdown: 196,
      max_drawdown_pct: 0.39,
    });
    const result = await fetchEquityCurve();
    expect(result.points).toHaveLength(2);
    expect(result.points[1].drawdown).toBe(196);
  });

  it("rejects a response where a point is missing equity", async () => {
    mockFetchOnce({
      points: [{ closed_at: "2026-07-14T11:30:00Z", drawdown: 0 }],
      ending_equity: 50000,
      max_drawdown: 0,
      max_drawdown_pct: 0,
    });
    await expect(fetchEquityCurve()).rejects.toMatchObject({ kind: "invalid_response" });
  });
});

describe("fetchBreakdown", () => {
  const originalFetch = global.fetch;
  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("calls the same-origin proxy, not the backend directly", async () => {
    mockFetchOnce({ by_session: [], by_setup: [], by_weekday: [] });
    await fetchBreakdown();
    expect(global.fetch).toHaveBeenCalledWith("/api/proxy/analytics/breakdown", { cache: "no-store" });
  });

  it("parses empty breakdown groups", async () => {
    mockFetchOnce({ by_session: [], by_setup: [], by_weekday: [] });
    const result = await fetchBreakdown();
    expect(result.by_session).toHaveLength(0);
    expect(result.by_setup).toHaveLength(0);
    expect(result.by_weekday).toHaveLength(0);
  });

  it("parses populated breakdown groups", async () => {
    mockFetchOnce({
      by_session: [{ key: "NY_AM", total_trades: 5, win_rate_pct: 80, total_realized_pnl: 500 }],
      by_setup: [{ key: "BRK", total_trades: 3, win_rate_pct: 66.7, total_realized_pnl: 300 }],
      by_weekday: [{ key: "Monday", total_trades: 2, win_rate_pct: 50, total_realized_pnl: 0 }],
    });
    const result = await fetchBreakdown();
    expect(result.by_session[0].key).toBe("NY_AM");
    expect(result.by_setup[0].total_realized_pnl).toBe(300);
  });

  it("rejects a response where by_setup is not an array", async () => {
    mockFetchOnce({ by_session: [], by_setup: "none", by_weekday: [] });
    await expect(fetchBreakdown()).rejects.toMatchObject({ kind: "invalid_response" });
  });

  it("throws network_error when fetch itself throws", async () => {
    global.fetch = vi.fn(async () => {
      throw new TypeError("fetch failed");
    }) as unknown as typeof fetch;
    await expect(fetchBreakdown()).rejects.toMatchObject({ kind: "network_error" });
  });
});
