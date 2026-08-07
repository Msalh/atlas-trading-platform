import { describe, expect, it } from "vitest";
import { projectAdvisory } from "@/lib/advisoryApi";

function response() {
  return {
    schema_version: "trader_now_response.v2",
    input_snapshot_at: "2026-08-06T12:00:00Z",
    identity: { product: "MNQ", symbol: "MNQ", timeframe: "5m" },
    trust: { status: "trusted" },
    source_trust: {
      overall: "trusted",
      structural_validity: "valid",
      freshness: { status: "current", latest_closed_at: "2026-08-06T12:00:00Z" },
    },
    market: {
      latest_closed_at: "2026-08-06T12:00:00Z",
      latest_bar: { occurred_at: "2026-08-06T12:00:00Z", close: { value: 21234.25 } },
    },
    context: {
      data: { session: { phase: "rth" }, volatility: { regime: "expanded" } },
    },
    strategy: {
      availability: { status: "available" },
      decisions: [{
        disposition: "candidate",
        direction: "long",
        stop: { value: 21220 },
        target: { value: 21260 },
        confidence: 0.81,
        setup_ids: ["displacement"],
      }],
    },
  };
}

describe("projectAdvisory", () => {
  it("uses only the matching completed confirmation-candle close as entry", () => {
    expect(projectAdvisory(response())).toEqual({
      state: "long_candidate",
      instrument: "MNQ",
      timeframe: "5m",
      dataTimestamp: "2026-08-06T12:00:00Z",
      freshness: "current",
      entryPrice: 21234.25,
      stopLoss: 21220,
      takeProfit: 21260,
      confidence: 0.81,
      setupQuality: "displacement",
      sessionPhase: "rth",
      volatilityRegime: "expanded",
      reason: "Deterministic candidate from the latest trusted TraderNow state.",
    });
  });

  it("projects an available response with no candidate truthfully", () => {
    const body = response();
    body.strategy.decisions = [];
    const result = projectAdvisory(body);
    expect(result.state).toBe("no_candidate");
    expect(result.entryPrice).toBeNull();
    expect(result.stopLoss).toBeNull();
    expect(result.takeProfit).toBeNull();
  });

  it.each([
    ["stale evidence", (body: ReturnType<typeof response>) => { body.source_trust.freshness.status = "stale"; }],
    ["untrusted evidence", (body: ReturnType<typeof response>) => { body.trust.status = "untrusted"; }],
    ["missing stop", (body: ReturnType<typeof response>) => { body.strategy.decisions[0].stop = null as never; }],
    ["missing target", (body: ReturnType<typeof response>) => { body.strategy.decisions[0].target = null as never; }],
    ["missing confidence", (body: ReturnType<typeof response>) => { body.strategy.decisions[0].confidence = null as never; }],
    ["missing setup", (body: ReturnType<typeof response>) => { body.strategy.decisions[0].setup_ids = []; }],
    ["mismatched latest bar", (body: ReturnType<typeof response>) => { body.market.latest_bar.occurred_at = "2026-08-06T12:05:00Z"; }],
    ["mismatched market close", (body: ReturnType<typeof response>) => { body.market.latest_closed_at = "2026-08-06T11:55:00Z"; }],
    ["ambiguous candidates", (body: ReturnType<typeof response>) => { body.strategy.decisions.push({ ...body.strategy.decisions[0] }); }],
  ])("fails closed for %s", (_label, mutate) => {
    const body = response();
    mutate(body);
    const result = projectAdvisory(body);
    expect(result.state).toBe("unavailable");
    expect(result.entryPrice).toBeNull();
    expect(result.stopLoss).toBeNull();
    expect(result.takeProfit).toBeNull();
  });
});
