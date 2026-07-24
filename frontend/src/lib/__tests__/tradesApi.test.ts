import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchCurrentTrade, fetchTradeDetail, fetchTradeList, Trade } from "@/lib/tradesApi";

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
  atr: 12.5,
  ema_distance_atr: 1.2,
  regime_slope_pct: 0.8,
  session: "London",
  pmt_relay_diagnostics: null,
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

describe("fetchTradeDetail", () => {
  const originalFetch = global.fetch;
  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("calls the same-origin proxy at trades/<id>", async () => {
    mockFetchOnce({ trade: OPEN_TRADE, timeline: [] });
    await fetchTradeDetail("abc123");
    expect(global.fetch).toHaveBeenCalledWith("/api/proxy/trades/abc123", { cache: "no-store" });
  });

  it("passes a real production id shape through the encodeURIComponent call unchanged", async () => {
    // JS's encodeURIComponent leaves "!" unescaped (it's in its unreserved
    // set) - this proves the real-shaped id still reaches the right path,
    // not that every character gets percent-escaped (see the next test for
    // a character that genuinely does).
    mockFetchOnce({ trade: OPEN_TRADE, timeline: [] });
    await fetchTradeDetail("E2E-MNQ1!-1783579500000");
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/proxy/trades/E2E-MNQ1!-1783579500000",
      { cache: "no-store" },
    );
  });

  it("URL-encodes a character that genuinely needs escaping", async () => {
    mockFetchOnce({ trade: OPEN_TRADE, timeline: [] });
    await fetchTradeDetail("id with space");
    expect(global.fetch).toHaveBeenCalledWith("/api/proxy/trades/id%20with%20space", { cache: "no-store" });
  });

  it("resolves to null on a 404 (no trade found) instead of throwing", async () => {
    mockFetchOnce({ ok: false, error: "not found" }, 404);
    const result = await fetchTradeDetail("does-not-exist");
    expect(result).toBeNull();
  });

  it("parses a populated trade detail response with a timeline", async () => {
    mockFetchOnce({
      trade: OPEN_TRADE,
      timeline: [
        { type: "entry_received", at: "2026-07-24T11:20:00Z", direction: "long", entry_price: 29605.5, sl: 29580, tp: 29650 },
        { type: "pmt_forwarded", at: "2026-07-24T11:20:00Z", status_code: 200 },
      ],
    });
    const result = await fetchTradeDetail("abc123");
    expect(result?.trade.correlation_id).toBe("abc123");
    expect(result?.timeline).toHaveLength(2);
    expect(result?.timeline[0].type).toBe("entry_received");
  });

  it("parses a trade with populated pmt_relay_diagnostics", async () => {
    mockFetchOnce({
      trade: {
        ...OPEN_TRADE,
        pmt_relay_diagnostics: {
          attempted_at: "2026-07-24T11:20:00Z",
          url: "https://pmt.example.com/webhook",
          method: "POST",
          payload: { data: "MNQU6", price: "29605.50", date: "2026-07-24" },
          status_code: 200,
          response_body: "{\"ok\":true}",
          exception: null,
          duration_ms: 142.3,
        },
      },
      timeline: [],
    });
    const result = await fetchTradeDetail("abc123");
    expect(result?.trade.pmt_relay_diagnostics?.status_code).toBe(200);
  });

  it("rejects a response with an invalid timeline event type", async () => {
    mockFetchOnce({ trade: OPEN_TRADE, timeline: [{ type: "not_a_real_type", at: null }] });
    await expect(fetchTradeDetail("abc123")).rejects.toMatchObject({ kind: "invalid_response" });
  });

  it("propagates a non-404 error (e.g. 401) rather than returning null", async () => {
    mockFetchOnce({ ok: false, error: "missing or invalid API key" }, 401);
    await expect(fetchTradeDetail("abc123")).rejects.toMatchObject({ kind: "upstream_error" });
  });

  it("throws network_error when fetch itself throws", async () => {
    global.fetch = vi.fn(async () => {
      throw new TypeError("fetch failed");
    }) as unknown as typeof fetch;
    await expect(fetchTradeDetail("abc123")).rejects.toMatchObject({ kind: "network_error" });
  });
});
