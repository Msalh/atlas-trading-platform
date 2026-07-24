import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiFetchError, fetchStatus } from "@/lib/statusApi";

function mockFetchOnce(body: unknown, status = 200) {
  global.fetch = vi.fn(async () => new Response(JSON.stringify(body), { status })) as unknown as typeof fetch;
}

const VALID_STATUS = {
  database: { ok: true, reason: null, detail: "ok" },
  tradingview: { last_webhook_at: null, last_webhook_type: null },
  pickmytrade: { configured: false, last_forward_at: null, last_forward_ok: null, last_error: null },
  claude: { configured: false, last_analysis_at: null, last_error: null },
};

describe("fetchStatus", () => {
  const originalFetch = global.fetch;
  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("calls the same-origin proxy, not the backend directly", async () => {
    mockFetchOnce(VALID_STATUS);
    await fetchStatus();
    expect(global.fetch).toHaveBeenCalledWith("/api/proxy/status", { cache: "no-store" });
  });

  it("parses a healthy status response", async () => {
    mockFetchOnce(VALID_STATUS);
    const result = await fetchStatus();
    expect(result.database.ok).toBe(true);
    expect(result.claude.configured).toBe(false);
  });

  it("parses a populated status response", async () => {
    mockFetchOnce({
      database: { ok: false, reason: "ping_failed", detail: "database ping failed - see server logs for details" },
      tradingview: { last_webhook_at: "2026-07-23T20:30:00Z", last_webhook_type: "market_state.ingested" },
      pickmytrade: {
        configured: true,
        last_forward_at: "2026-07-23T20:00:00Z",
        last_forward_ok: true,
        last_error: null,
      },
      claude: { configured: true, last_analysis_at: "2026-07-23T19:00:00Z", last_error: "timeout" },
    });
    const result = await fetchStatus();
    expect(result.database.ok).toBe(false);
    expect(result.pickmytrade.last_forward_ok).toBe(true);
    expect(result.claude.last_error).toBe("timeout");
  });

  it("throws not_found on a 404", async () => {
    mockFetchOnce({ ok: false, error: "not found" }, 404);
    await expect(fetchStatus()).rejects.toMatchObject({ kind: "not_found" satisfies ApiFetchError["kind"] });
  });

  it("rejects a response missing the claude field", async () => {
    mockFetchOnce({
      database: { ok: true, reason: null, detail: "ok" },
      tradingview: { last_webhook_at: null, last_webhook_type: null },
      pickmytrade: { configured: false, last_forward_at: null, last_forward_ok: null, last_error: null },
    });
    await expect(fetchStatus()).rejects.toMatchObject({ kind: "invalid_response" });
  });

  it("throws network_error when fetch itself throws", async () => {
    global.fetch = vi.fn(async () => {
      throw new TypeError("fetch failed");
    }) as unknown as typeof fetch;
    await expect(fetchStatus()).rejects.toMatchObject({ kind: "network_error" });
  });
});
