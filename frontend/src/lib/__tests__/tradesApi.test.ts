import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchCurrentTrade, fetchTradeList, Trade } from "@/lib/tradesApi";

function mockFetchOnce(body: unknown, status = 200) {
  global.fetch = vi.fn(async () => new Response(JSON.stringify(body), { status })) as unknown as typeof fetch;
}

const OPEN_TRADE: Trade = {
  correlation_id: "abc123",
  received_at: "2026-07-24T11:20:00Z",
  direction: "long",
  setup_tag: "BRK",
  entry_price: 29605.5,
  sl: 29580,
  tp: 29650,
  status: "open",
  current_price: 29610,
  unrealized_pnl: 40,
  realized_pnl: null,
  pmt_forwarded: true,
  pmt_error: null,
};

describe("fetchCurrentTrade", () => {
  const originalFetch = global.fetch;
  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("calls the same-origin proxy, not the backend directly", async () => {
    mockFetchOnce({ open: false, trade: null });
    await fetchCurrentTrade();
    expect(global.fetch).toHaveBeenCalledWith("/api/proxy/trades/current", { cache: "no-store" });
  });

  it("parses a flat (no open trade) response", async () => {
    mockFetchOnce({ open: false, trade: null });
    const result = await fetchCurrentTrade();
    expect(result.open).toBe(false);
    expect(result.trade).toBeNull();
  });

  it("parses an open trade response", async () => {
    mockFetchOnce({ open: true, trade: OPEN_TRADE });
    const result = await fetchCurrentTrade();
    expect(result.open).toBe(true);
    expect(result.trade?.direction).toBe("long");
  });

  it("rejects a trade with an invalid direction", async () => {
    mockFetchOnce({ open: true, trade: { ...OPEN_TRADE, direction: "sideways" } });
    await expect(fetchCurrentTrade()).rejects.toMatchObject({ kind: "invalid_response" });
  });

  it("throws network_error when fetch itself throws", async () => {
    global.fetch = vi.fn(async () => {
      throw new TypeError("fetch failed");
    }) as unknown as typeof fetch;
    await expect(fetchCurrentTrade()).rejects.toMatchObject({ kind: "network_error" });
  });
});

describe("fetchTradeList", () => {
  const originalFetch = global.fetch;
  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("forwards limit and status as query params", async () => {
    mockFetchOnce({ count: 0, trades: [] });
    await fetchTradeList({ limit: 50, status: "open" });
    expect(global.fetch).toHaveBeenCalledWith("/api/proxy/trades?limit=50&status=open", { cache: "no-store" });
  });

  it("omits query params entirely when not provided", async () => {
    mockFetchOnce({ count: 0, trades: [] });
    await fetchTradeList();
    expect(global.fetch).toHaveBeenCalledWith("/api/proxy/trades", { cache: "no-store" });
  });

  it("parses a populated trade list", async () => {
    mockFetchOnce({ count: 1, trades: [OPEN_TRADE] });
    const result = await fetchTradeList({ limit: 50 });
    expect(result.count).toBe(1);
    expect(result.trades[0].correlation_id).toBe("abc123");
  });

  it("rejects a response where trades is not an array", async () => {
    mockFetchOnce({ count: 1, trades: "not-an-array" });
    await expect(fetchTradeList()).rejects.toMatchObject({ kind: "invalid_response" });
  });

  it("throws upstream_error on a non-200/404/422 status", async () => {
    mockFetchOnce({ ok: false, error: "invalid status 'bogus'" }, 400);
    await expect(fetchTradeList({ status: "bogus" })).rejects.toMatchObject({ kind: "upstream_error" });
  });
});
