import { describe, expect, it } from "vitest";
import { ALLOWED_PROXY_PATHS, filterAllowedParams, isAllowedProxyPath } from "@/lib/proxyAllowlist";

describe("isAllowedProxyPath", () => {
  it("allows every exact documented path", () => {
    for (const path of Object.keys(ALLOWED_PROXY_PATHS)) {
      expect(isAllowedProxyPath(path)).toBe(true);
    }
  });

  it("rejects a path not on the allowlist", () => {
    expect(isAllowedProxyPath("trades")).toBe(false);
    expect(isAllowedProxyPath("market-state/export")).toBe(false);
    expect(isAllowedProxyPath("health")).toBe(false);
    expect(isAllowedProxyPath("status")).toBe(false);
  });

  it("rejects a near-miss of an allowed path (no prefix matching)", () => {
    expect(isAllowedProxyPath("research/re1/summary/extra")).toBe(false);
    expect(isAllowedProxyPath("research")).toBe(false);
    expect(isAllowedProxyPath("setup-engine")).toBe(false);
  });

  it("is exact-match, not case-insensitive", () => {
    expect(isAllowedProxyPath("Research/Re1/Summary")).toBe(false);
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

  it("returns an empty set of params for a path that declares none", () => {
    const incoming = new URLSearchParams({ symbol: "MNQ1!", anything: "x" });
    const filtered = filterAllowedParams("research/re1/summary", incoming);
    expect([...filtered.keys()]).toEqual([]);
  });

  it("returns an empty set for an unapproved path entirely", () => {
    const incoming = new URLSearchParams({ symbol: "MNQ1!" });
    const filtered = filterAllowedParams("not-a-real-path", incoming);
    expect([...filtered.keys()]).toEqual([]);
  });

  it("never forwards an authorization-shaped query param that was not declared", () => {
    const incoming = new URLSearchParams({ symbol: "MNQ1!", timeframe: "5m", api_key: "secret-value" });
    const filtered = filterAllowedParams("rule-engine/latest", incoming);
    expect(filtered.has("api_key")).toBe(false);
    expect(filtered.toString()).not.toContain("secret-value");
  });
});
