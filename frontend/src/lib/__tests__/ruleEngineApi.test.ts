import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchLatestRuleEngineOutputViaProxy } from "@/lib/ruleEngineApi";

function mockFetchOnce(body: unknown, status = 200) {
  global.fetch = vi.fn(async () => new Response(JSON.stringify(body), { status })) as unknown as typeof fetch;
}

describe("fetchLatestRuleEngineOutputViaProxy", () => {
  const originalFetch = global.fetch;
  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("parses a found=true response with a computed and an insufficient_data fact", async () => {
    mockFetchOnce({
      ok: true,
      found: true,
      data: {
        schema_version: "1.0",
        symbol: "MNQU6",
        timeframe: "5m",
        occurred_at: "2026-07-20T11:55:00Z",
        facts: [
          { name: "trend_5m", status: "computed", value: "up", definition_version: "1.0", evidence: {} },
          { name: "reclaim", status: "insufficient_data", definition_version: "1.0", reason: "not enough history" },
        ],
      },
    });

    const result = await fetchLatestRuleEngineOutputViaProxy("MNQU6", "5m");
    expect(result.found).toBe(true);
    expect(result.data?.facts).toHaveLength(2);
    expect(result.data?.facts[0].status).toBe("computed");
    expect(result.data?.facts[1].status).toBe("insufficient_data");
  });

  it("parses a found=false response", async () => {
    mockFetchOnce({ ok: true, found: false, data: null });
    const result = await fetchLatestRuleEngineOutputViaProxy("MNQU6", "5m");
    expect(result.found).toBe(false);
    expect(result.data).toBeNull();
  });

  it("requests through the same-origin proxy path with symbol/timeframe params", async () => {
    let capturedUrl = "";
    global.fetch = vi.fn(async (url: string | URL) => {
      capturedUrl = String(url);
      return new Response(JSON.stringify({ ok: true, found: false, data: null }), { status: 200 });
    }) as unknown as typeof fetch;

    await fetchLatestRuleEngineOutputViaProxy("MNQU6", "5m");
    expect(capturedUrl).toBe("/api/proxy/rule-engine/latest?symbol=MNQU6&timeframe=5m");
  });

  it("rejects a computed fact whose value is neither boolean nor string", async () => {
    mockFetchOnce({
      ok: true,
      found: true,
      data: {
        schema_version: "1.0",
        symbol: "MNQU6",
        timeframe: "5m",
        occurred_at: "t",
        facts: [{ name: "x", status: "computed", value: 42, definition_version: "1.0", evidence: {} }],
      },
    });
    await expect(fetchLatestRuleEngineOutputViaProxy("MNQU6", "5m")).rejects.toMatchObject({ kind: "invalid_response" });
  });
});
