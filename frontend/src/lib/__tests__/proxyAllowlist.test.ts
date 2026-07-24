import { describe, expect, it } from "vitest";
import {
  ALLOWED_PROXY_ROUTES,
  filterAllowedParams,
  isAllowedProxyMethod,
  isAllowedProxyPath,
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

  it("no path in the real production table declares a POST config (Slice A.1 regression)", () => {
    // research/promotion/decide (or any other write path) must not reappear
    // in production config outside its own slice's own review - this is the
    // direct, mechanical proof that Slice A.1's removal actually holds.
    const pathsWithPost = Object.entries(ALLOWED_PROXY_ROUTES)
      .filter(([, config]) => config.POST != null)
      .map(([path]) => path);
    expect(pathsWithPost).toEqual([]);
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
