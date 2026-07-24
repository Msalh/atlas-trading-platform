import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ApiFetchError,
  fetchAiNotes,
  fetchAiReports,
  fetchIntelligence,
  triggerReport,
} from "@/lib/aiApi";

const NOTE = {
  id: 1,
  trade_correlation_id: "corr-1",
  note_type: "entry_score",
  created_at: "2026-07-24T10:00:00Z",
  model: "claude",
  score: 8,
  score_label: "High Confidence",
  content: "Strong setup",
  error: null,
  expected_r: 1.5,
  historical_win_rate_pct: 70,
  similar_trade_count: 10,
  factors: [{
    name: "atr",
    entry_value: 1,
    winners_median: 1.2,
    losers_median: 0.8,
    favorable: true,
  }],
};

const SUMMARY = {
  total_trades: 10,
  wins: 7,
  losses: 3,
  win_rate_pct: 70,
  gross_profit: 1000,
  gross_loss: -300,
  profit_factor: 3.33,
  expectancy: 70,
  avg_win: 142.86,
  avg_loss: -100,
  avg_r: 1.5,
  r_multiple_sample_size: 10,
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe("fetchAiNotes", () => {
  it("uses the proxy and constructs every supported query parameter", async () => {
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ count: 1, notes: [NOTE] }), { status: 200 }),
    );

    const result = await fetchAiNotes({
      tradeCorrelationId: "corr-1",
      noteType: "entry_score",
      limit: 1,
    });

    expect(result.notes).toHaveLength(1);
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/proxy/ai/notes?trade_correlation_id=corr-1&note_type=entry_score&limit=1",
      { cache: "no-store" },
    );
  });

  it("rejects a malformed successful response", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ count: 1, notes: [{ id: "wrong" }] }), { status: 200 }),
    );
    await expect(fetchAiNotes()).rejects.toMatchObject({ kind: "invalid_response" });
  });
});

describe("fetchAiReports", () => {
  it("constructs period and limit query parameters", async () => {
    const report = { ...NOTE, note_type: "weekly_report" };
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ count: 1, reports: [report] }), { status: 200 }),
    );

    await fetchAiReports({ period: "weekly", limit: 10 });

    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/proxy/ai/reports?period=weekly&limit=10",
      { cache: "no-store" },
    );
  });

  it("preserves structured non-OK errors", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ ok: false, error: "bad period" }), { status: 400 }),
    );
    await expect(fetchAiReports()).rejects.toMatchObject({
      kind: "upstream_error",
      message: "bad period",
    });
  });
});

describe("triggerReport", () => {
  it.each(["daily", "weekly"] as const)("POSTs %s with no request body and preserves the 202 response", async (period) => {
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ ok: true, status: "generating", period }), { status: 202 }),
    );

    await expect(triggerReport(period)).resolves.toEqual({ ok: true, status: "generating", period });
    expect(fetchSpy).toHaveBeenCalledWith(`/api/proxy/ai/reports/${period}`, {
      method: "POST",
      headers: undefined,
      body: undefined,
      cache: "no-store",
    });
  });

  it("validates the trigger response", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ ok: true, status: "done", period: "daily" }), { status: 202 }),
    );
    await expect(triggerReport("daily")).rejects.toMatchObject({ kind: "invalid_response" });
  });
});

describe("fetchIntelligence", () => {
  it("encodes the correlation ID and validates the snapshot", async () => {
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify({
        correlation_id: "id with space",
        similar_trade_count: 10,
        confidence_score: 8,
        confidence_label: "High Confidence",
        summary: SUMMARY,
        factors: NOTE.factors,
      }), { status: 200 }),
    );

    await fetchIntelligence("id with space");
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/proxy/ai/intelligence/id%20with%20space",
      { cache: "no-store" },
    );
  });

  it("maps a backend 404 to null", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ ok: false, error: "no trade found" }), { status: 404 }),
    );
    await expect(fetchIntelligence("missing")).resolves.toBeNull();
  });

  it("maps a thrown fetch to a network error", async () => {
    vi.spyOn(global, "fetch").mockRejectedValue(new Error("offline"));
    await expect(fetchIntelligence("corr-1")).rejects.toMatchObject({
      name: "ApiFetchError",
      kind: "network_error",
      message: "Could not reach the backend.",
    } satisfies Partial<ApiFetchError>);
  });
});
