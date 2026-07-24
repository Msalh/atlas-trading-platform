import { describe, expect, it } from "vitest";
import {
  ALLOWED_PROXY_ROUTES,
  filterAllowedParams,
  isAllowedProxyMethod,
  isAllowedProxyPath,
  parseAiIntelligencePath,
  parseTradeDetailPath,
  ProxyRouteConfig,
  projectAllowedBody,
} from "@/lib/proxyAllowlist";

// A local, test-only route table - never merged into ALLOWED_PROXY_ROUTES -
// used to exercise POST/projection behavior in isolation. Sprint 10 Slice A.1
// deliberately removed the only real POST-configured production path
// (research/promotion/decide belongs to Slice E - see proxyAllowlist.ts's
// own comment), so the mechanism itself is proven here instead, against a
// fixture, rather than against a real endpoint no consuming UI uses yet.
const TEST_POST_PATH = "test-fixture/post-only";
const FIXTURE_ROUTES: Readonly<Record<string, ProxyRouteConfig>> = {
  [TEST_POST_PATH]: { POST: { bodyFields: ["hypothesis_id", "decision", "reviewer", "rationale"] } },
};

describe("isAllowedProxyPath", () => {
  it("allows every exact documented path", () => {
    for (const path of Object.keys(ALLOWED_PROXY_ROUTES)) {
      expect(isAllowedProxyPath(path)).toBe(true);
    }
  });

  it("rejects a path not on the allowlist", () => {
    // "trades/detail" is not, and never was, a static table entry - it's
    // correctly false here. Since Sprint 11A Group 6, route.ts separately
    // ALSO accepts it through parseTradeDetailPath (as trade id "detail") -
    // that's a different mechanism this function has no knowledge of and
    // never will; see the parseTradeDetailPath describe block below.
    expect(isAllowedProxyPath("trades/detail")).toBe(false);
    expect(isAllowedProxyPath("market-state/export")).toBe(false);
    expect(isAllowedProxyPath("health")).toBe(false);
  });

  it("allows status - Sprint 10 Slice B's Research Overview reads it through the secure proxy, never lib/api.ts", () => {
    expect(isAllowedProxyPath("status")).toBe(true);
    expect(isAllowedProxyMethod("status", "GET")).toBe(true);
  });

  it("allows risk - Sprint 11A Group 0B's riskApi.ts reads it through the secure proxy, no params", () => {
    expect(isAllowedProxyPath("risk")).toBe(true);
    expect(isAllowedProxyMethod("risk", "GET")).toBe(true);
    expect(filterAllowedParams("risk", new URLSearchParams({ foo: "bar" })).toString()).toBe("");
  });

  it("allows activity with only limit forwarded - Sprint 11A Group 5's Activity reads", () => {
    expect(isAllowedProxyPath("activity")).toBe(true);
    expect(isAllowedProxyMethod("activity", "GET")).toBe(true);
    expect(
      filterAllowedParams("activity", new URLSearchParams({ limit: "150", extra: "drop-me" })).toString(),
    ).toBe("limit=150");
  });

  it("allows analytics/summary, analytics/equity-curve, and analytics/breakdown - Sprint 11A Group 4's Analytics reads", () => {
    expect(isAllowedProxyPath("analytics/summary")).toBe(true);
    expect(isAllowedProxyMethod("analytics/summary", "GET")).toBe(true);
    expect(isAllowedProxyPath("analytics/equity-curve")).toBe(true);
    expect(isAllowedProxyMethod("analytics/equity-curve", "GET")).toBe(true);
    expect(isAllowedProxyPath("analytics/breakdown")).toBe(true);
    expect(isAllowedProxyMethod("analytics/breakdown", "GET")).toBe(true);
  });

  it("allows trades/current, trades, and stats/today - Sprint 11A Group 2's Dashboard reads", () => {
    expect(isAllowedProxyPath("trades/current")).toBe(true);
    expect(isAllowedProxyMethod("trades/current", "GET")).toBe(true);

    expect(isAllowedProxyPath("trades")).toBe(true);
    expect(isAllowedProxyMethod("trades", "GET")).toBe(true);
    expect(
      filterAllowedParams("trades", new URLSearchParams({ limit: "50", status: "open", extra: "drop-me" })).toString(),
    ).toBe("limit=50&status=open");

    expect(isAllowedProxyPath("stats/today")).toBe(true);
    expect(isAllowedProxyMethod("stats/today", "GET")).toBe(true);
  });

  it("rejects a near-miss of an allowed path (no prefix matching)", () => {
    expect(isAllowedProxyPath("research/re1/summary/extra")).toBe(false);
    expect(isAllowedProxyPath("research")).toBe(false);
    expect(isAllowedProxyPath("setup-engine")).toBe(false);
  });

  it("is exact-match, not case-insensitive", () => {
    expect(isAllowedProxyPath("Research/Re1/Summary")).toBe(false);
  });

  it("only the two approved Group 7 report triggers declare POST", () => {
    const pathsWithPost = Object.entries(ALLOWED_PROXY_ROUTES)
      .filter(([, config]) => config.POST != null)
      .map(([path]) => path);
    expect(pathsWithPost).toEqual(["ai/reports/daily", "ai/reports/weekly"]);
  });

  it("allows only the exact AI paths and methods with declared query params", () => {
    expect(isAllowedProxyMethod("ai/notes", "GET")).toBe(true);
    expect(isAllowedProxyMethod("ai/notes", "POST")).toBe(false);
    expect(isAllowedProxyMethod("ai/reports", "GET")).toBe(true);
    expect(isAllowedProxyMethod("ai/reports", "POST")).toBe(false);
    expect(isAllowedProxyMethod("ai/reports/daily", "POST")).toBe(true);
    expect(isAllowedProxyMethod("ai/reports/daily", "GET")).toBe(false);
    expect(isAllowedProxyMethod("ai/reports/weekly", "POST")).toBe(true);
    expect(isAllowedProxyMethod("ai/reports/monthly", "POST")).toBe(false);
    expect(
      filterAllowedParams(
        "ai/notes",
        new URLSearchParams({ trade_correlation_id: "c1", note_type: "entry_score", limit: "1", extra: "drop" }),
      ).toString(),
    ).toBe("trade_correlation_id=c1&note_type=entry_score&limit=1");
  });
});

describe("isAllowedProxyMethod", () => {
  it("allows GET for every path that declares a GET config", () => {
    expect(isAllowedProxyMethod("rule-engine/latest", "GET")).toBe(true);
    expect(isAllowedProxyMethod("research/dataset-health", "GET")).toBe(true);
    expect(isAllowedProxyMethod("research/lineage", "GET")).toBe(true);
  });

  it("allows GET for the three Sprint 10 Slice B Research Overview paths", () => {
    expect(isAllowedProxyMethod("status", "GET")).toBe(true);
    expect(isAllowedProxyMethod("research/leaderboard", "GET")).toBe(true);
    expect(isAllowedProxyMethod("research/promotion", "GET")).toBe(true);
  });

  it("allows GET for research/promotion/candidates - Sprint 10 Slice E's Promotion Queue read", () => {
    expect(isAllowedProxyMethod("research/promotion/candidates", "GET")).toBe(true);
    expect(isAllowedProxyMethod("research/promotion/candidates", "POST")).toBe(false);
  });

  it("rejects research/promotion/decide entirely - it is not a production path (Slice A.1 regression)", () => {
    expect(isAllowedProxyMethod("research/promotion/decide", "POST")).toBe(false);
    expect(isAllowedProxyMethod("research/promotion/decide", "GET")).toBe(false);
    expect(isAllowedProxyPath("research/promotion/decide")).toBe(false);
  });

  it("rejects both methods for a path not on the allowlist at all", () => {
    // Same caveat as isAllowedProxyPath's own test above: this function
    // only ever consults the static table, so "trades/detail" is correctly
    // false here regardless of what parseTradeDetailPath separately does
    // with it.
    expect(isAllowedProxyMethod("trades/detail", "GET")).toBe(false);
    expect(isAllowedProxyMethod("trades/detail", "POST")).toBe(false);
  });

  it("allows POST for a path with a POST config, using an injected route table", () => {
    expect(isAllowedProxyMethod(TEST_POST_PATH, "POST", FIXTURE_ROUTES)).toBe(true);
    expect(isAllowedProxyMethod(TEST_POST_PATH, "GET", FIXTURE_ROUTES)).toBe(false);
  });

  it("defaults to the real production table when no route table is injected", () => {
    expect(isAllowedProxyMethod("research/lineage", "GET")).toBe(true);
    expect(isAllowedProxyMethod(TEST_POST_PATH, "POST")).toBe(false);
  });
});

describe("filterAllowedParams", () => {
  it("forwards only the declared params for a path", () => {
    const incoming = new URLSearchParams({ symbol: "MNQ1!", timeframe: "5m", extra: "drop-me" });
    const filtered = filterAllowedParams("rule-engine/latest", incoming);
    expect(filtered.get("symbol")).toBe("MNQ1!");
    expect(filtered.get("timeframe")).toBe("5m");
    expect(filtered.has("extra")).toBe(false);
  });

  it("forwards window only for the one path that declares it", () => {
    const incoming = new URLSearchParams({ symbol: "MNQ1!", timeframe: "5m", window: "500" });
    expect(filterAllowedParams("setup-engine/latest", incoming).has("window")).toBe(false);
    expect(filterAllowedParams("setup-engine/episodes/live", incoming).get("window")).toBe("500");
  });

  it("forwards promotion_id/validation_id only for the lineage path", () => {
    const incoming = new URLSearchParams({ promotion_id: "p1", validation_id: "v1" });
    const filtered = filterAllowedParams("research/lineage", incoming);
    expect(filtered.get("promotion_id")).toBe("p1");
    expect(filtered.get("validation_id")).toBe("v1");
  });

  it("returns an empty set of params for a path that declares none", () => {
    const incoming = new URLSearchParams({ symbol: "MNQ1!", anything: "x" });
    const filtered = filterAllowedParams("research/re1/summary", incoming);
    expect([...filtered.keys()]).toEqual([]);
  });

  it("returns an empty set of params for an unapproved path entirely", () => {
    const incoming = new URLSearchParams({ symbol: "MNQ1!" });
    const filtered = filterAllowedParams("not-a-real-path", incoming);
    expect([...filtered.keys()]).toEqual([]);
  });

  it("returns an empty set of params for a path that only declares a POST config", () => {
    const incoming = new URLSearchParams({ hypothesis_id: "h1" });
    const filtered = filterAllowedParams(TEST_POST_PATH, incoming, FIXTURE_ROUTES);
    expect([...filtered.keys()]).toEqual([]);
  });

  it("never forwards an authorization-shaped query param that was not declared", () => {
    const incoming = new URLSearchParams({ symbol: "MNQ1!", timeframe: "5m", api_key: "secret-value" });
    const filtered = filterAllowedParams("rule-engine/latest", incoming);
    expect(filtered.has("api_key")).toBe(false);
    expect(filtered.toString()).not.toContain("secret-value");
  });
});

describe("projectAllowedBody", () => {
  it("forwards only the declared fields for a path", () => {
    const incoming = { hypothesis_id: "h1", decision: "approved", reviewer: "jane", rationale: "clears the bar" };
    const projected = projectAllowedBody(TEST_POST_PATH, incoming, FIXTURE_ROUTES);
    expect(projected).toEqual({ hypothesis_id: "h1", decision: "approved", reviewer: "jane", rationale: "clears the bar" });
  });

  it("drops any field not declared for the path", () => {
    const incoming = {
      hypothesis_id: "h1", decision: "approved", reviewer: "jane", rationale: "ok",
      evidence_snapshot_ref: "v1", realization_id: "attacker-supplied", promotion_id: "attacker-supplied",
    };
    const projected = projectAllowedBody(TEST_POST_PATH, incoming, FIXTURE_ROUTES);
    expect(projected.realization_id).toBeUndefined();
    expect(projected.promotion_id).toBeUndefined();
    expect(projected.evidence_snapshot_ref).toBeUndefined();
  });

  it("omits a declared field entirely rather than inventing a default when it is absent from the input", () => {
    const projected = projectAllowedBody(TEST_POST_PATH, { hypothesis_id: "h1" }, FIXTURE_ROUTES);
    expect(projected).toEqual({ hypothesis_id: "h1" });
    expect(Object.prototype.hasOwnProperty.call(projected, "reviewer")).toBe(false);
  });

  it("forwards a field's value as-is without checking its type - shape/name projection only, never a business check", () => {
    const projected = projectAllowedBody(TEST_POST_PATH, { hypothesis_id: 12345 }, FIXTURE_ROUTES);
    expect(projected.hypothesis_id).toBe(12345);
  });

  it("returns an empty object for a path that only declares a GET config", () => {
    expect(projectAllowedBody("research/dataset-health", { anything: "x" })).toEqual({});
  });

  it("returns an empty object for an unapproved path entirely", () => {
    expect(projectAllowedBody("not-a-real-path", { anything: "x" })).toEqual({});
  });

  it("returns an empty object for research/promotion/decide - it has no config in production (Slice A.1 regression)", () => {
    expect(projectAllowedBody("research/promotion/decide", { hypothesis_id: "h1" })).toEqual({});
  });

  it("defaults to the real production table when no route table is injected", () => {
    expect(projectAllowedBody("research/dataset-health", { anything: "x" })).toEqual({});
  });
});

describe("parseTradeDetailPath", () => {
  it("accepts the exact shape: trades/<non-empty id>", () => {
    expect(parseTradeDetailPath(["trades", "abc123"])).toBe("abc123");
  });

  it("accepts an id containing special characters (real correlation_id shapes seen in production)", () => {
    expect(parseTradeDetailPath(["trades", "E2E-MNQ1!-1783579500000"])).toBe("E2E-MNQ1!-1783579500000");
    expect(parseTradeDetailPath(["trades", "1784016900000"])).toBe("1784016900000");
  });

  it("rejects a bare trades path with no id (1 segment)", () => {
    expect(parseTradeDetailPath(["trades"])).toBeNull();
  });

  it("rejects an id with a trailing extra segment - /trades/{id}/anything", () => {
    expect(parseTradeDetailPath(["trades", "abc123", "anything"])).toBeNull();
  });

  it("rejects /trades/detail/test - not a real trade id, just an extra segment", () => {
    expect(parseTradeDetailPath(["trades", "detail", "test"])).toBeNull();
  });

  it("rejects an empty id segment", () => {
    expect(parseTradeDetailPath(["trades", ""])).toBeNull();
  });

  it("rejects a wrong first segment", () => {
    expect(parseTradeDetailPath(["other", "abc123"])).toBeNull();
    expect(parseTradeDetailPath(["Trades", "abc123"])).toBeNull(); // case-sensitive, matching every other exact-match check in this file
  });

  it("rejects an id segment with an embedded slash (a decoded-%2F smuggling attempt)", () => {
    // Simulates the case where Next.js has already decoded an inbound "%2F"
    // into a literal "/" character within a single raw path segment - the
    // array element itself carries the slash, not a genuinely-separate
    // third segment. parseTradeDetailPath must reject this explicitly, not
    // rely on an implicit join/resplit collapse to catch it.
    expect(parseTradeDetailPath(["trades", "abc/def"])).toBeNull();
  });

  it("rejects an implausibly long id (defensive bound)", () => {
    expect(parseTradeDetailPath(["trades", "x".repeat(257)])).toBeNull();
    expect(parseTradeDetailPath(["trades", "x".repeat(256)])).toBe("x".repeat(256));
  });

  it("rejects zero segments", () => {
    expect(parseTradeDetailPath([])).toBeNull();
  });
});

describe("parseAiIntelligencePath", () => {
  it("accepts exactly ai/intelligence/<non-empty id>", () => {
    expect(parseAiIntelligencePath(["ai", "intelligence", "corr-1"])).toBe("corr-1");
    expect(parseAiIntelligencePath(["ai", "intelligence", "E2E-MNQ1!-1783579500000"]))
      .toBe("E2E-MNQ1!-1783579500000");
  });

  it("rejects missing, extra, wrong, empty, embedded-slash, and overlong shapes", () => {
    expect(parseAiIntelligencePath(["ai", "intelligence"])).toBeNull();
    expect(parseAiIntelligencePath(["ai", "intelligence", "corr-1", "extra"])).toBeNull();
    expect(parseAiIntelligencePath(["ai", "other", "corr-1"])).toBeNull();
    expect(parseAiIntelligencePath(["AI", "intelligence", "corr-1"])).toBeNull();
    expect(parseAiIntelligencePath(["ai", "intelligence", ""])).toBeNull();
    expect(parseAiIntelligencePath(["ai", "intelligence", "a/b"])).toBeNull();
    expect(parseAiIntelligencePath(["ai", "intelligence", "x".repeat(257)])).toBeNull();
    expect(parseAiIntelligencePath(["ai", "intelligence", "x".repeat(256)])).toBe("x".repeat(256));
  });
});
