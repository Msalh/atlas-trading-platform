import { afterEach, describe, expect, it, vi } from "vitest";
import { ActivityEvent, fetchActivity } from "@/lib/activityApi";

function mockFetchOnce(body: unknown, status = 200) {
  global.fetch = vi.fn(async () => new Response(JSON.stringify(body), { status })) as unknown as typeof fetch;
}

const TRADE_EVENT: ActivityEvent = {
  id: "trade-abc123-entry",
  timestamp: "2026-07-24T11:20:00Z",
  category: "trading",
  severity: "info",
  title: "Entry received: BRK long",
  description: null,
  correlation_id: "abc123",
};

describe("fetchActivity", () => {
  const originalFetch = global.fetch;
  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("forwards limit as a query param, through the same-origin proxy", async () => {
    mockFetchOnce({ count: 0, events: [] });
    await fetchActivity({ limit: 150 });
    expect(global.fetch).toHaveBeenCalledWith("/api/proxy/activity?limit=150", { cache: "no-store" });
  });

  it("omits query params entirely when not provided", async () => {
    mockFetchOnce({ count: 0, events: [] });
    await fetchActivity();
    expect(global.fetch).toHaveBeenCalledWith("/api/proxy/activity", { cache: "no-store" });
  });

  it("parses an empty feed", async () => {
    mockFetchOnce({ count: 0, events: [] });
    const result = await fetchActivity({ limit: 150 });
    expect(result.events).toHaveLength(0);
  });

  it("parses a populated feed across categories and severities", async () => {
    mockFetchOnce({
      count: 2,
      events: [
        TRADE_EVENT,
        {
          id: "risk-daily-loss",
          timestamp: "2026-07-24T12:00:00Z",
          category: "risk",
          severity: "critical",
          title: "Daily loss limit breached",
          description: "Used 1050.00 of 1000.00 limit",
          correlation_id: null,
        },
      ],
    });
    const result = await fetchActivity({ limit: 150 });
    expect(result.events).toHaveLength(2);
    expect(result.events[0].category).toBe("trading");
    expect(result.events[1].severity).toBe("critical");
    expect(result.events[1].correlation_id).toBeNull();
  });

  it("rejects an event with an invalid category", async () => {
    mockFetchOnce({ count: 1, events: [{ ...TRADE_EVENT, category: "unknown-category" }] });
    await expect(fetchActivity()).rejects.toMatchObject({ kind: "invalid_response" });
  });

  it("rejects an event with an invalid severity", async () => {
    mockFetchOnce({ count: 1, events: [{ ...TRADE_EVENT, severity: "urgent" }] });
    await expect(fetchActivity()).rejects.toMatchObject({ kind: "invalid_response" });
  });

  it("throws network_error when fetch itself throws", async () => {
    global.fetch = vi.fn(async () => {
      throw new TypeError("fetch failed");
    }) as unknown as typeof fetch;
    await expect(fetchActivity()).rejects.toMatchObject({ kind: "network_error" });
  });
});
