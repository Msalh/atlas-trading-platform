import { describe, expect, it } from "vitest";
import { classifyFreshness, currentThresholdMinutes, staleAfterMinutes } from "@/lib/freshness";

const NOW = new Date("2026-07-20T12:00:00Z").getTime();

function minutesAgoIso(minutes: number): string {
  return new Date(NOW - minutes * 60_000).toISOString();
}

describe("threshold documentation (production-hardening amendment 5)", () => {
  it("current threshold is 1.5x the bar duration", () => {
    expect(currentThresholdMinutes("5m")).toBe(7.5);
    expect(currentThresholdMinutes("1m")).toBe(1.5);
    expect(currentThresholdMinutes("15m")).toBe(22.5);
    expect(currentThresholdMinutes("1h")).toBe(90);
  });

  it("stale threshold is max(3x bar duration, 5 minutes) - Sprint 16's isStale formula, reused verbatim", () => {
    expect(staleAfterMinutes("5m")).toBe(15);
    expect(staleAfterMinutes("1m")).toBe(5); // floor applies: 3*1=3 < 5
    expect(staleAfterMinutes("15m")).toBe(45);
    expect(staleAfterMinutes("1h")).toBe(180);
  });

  it("falls back to the 5m table entry for an unrecognized timeframe, never throws", () => {
    expect(currentThresholdMinutes("unknown")).toBe(7.5);
    expect(staleAfterMinutes("unknown")).toBe(15);
  });
});

describe("classifyFreshness", () => {
  it("is 'current' well within the current threshold", () => {
    expect(classifyFreshness(minutesAgoIso(1), "5m", NOW)).toBe("current");
  });

  it("is 'current' exactly at the 1.5x boundary (inclusive)", () => {
    expect(classifyFreshness(minutesAgoIso(7.5), "5m", NOW)).toBe("current");
  });

  it("is 'delayed' just past the current threshold", () => {
    expect(classifyFreshness(minutesAgoIso(7.6), "5m", NOW)).toBe("delayed");
  });

  it("is 'delayed' well within the delayed band", () => {
    expect(classifyFreshness(minutesAgoIso(10), "5m", NOW)).toBe("delayed");
  });

  it("is 'delayed' exactly at the stale boundary (inclusive)", () => {
    expect(classifyFreshness(minutesAgoIso(15), "5m", NOW)).toBe("delayed");
  });

  it("is 'stale' just past the stale threshold", () => {
    expect(classifyFreshness(minutesAgoIso(15.1), "5m", NOW)).toBe("stale");
  });

  it("is 'stale' well past the stale threshold", () => {
    expect(classifyFreshness(minutesAgoIso(120), "5m", NOW)).toBe("stale");
  });

  it("respects a longer timeframe's proportionally larger thresholds", () => {
    // 20 minutes old is "current" for a 1h bar (threshold 90min) but
    // would be "stale" for a 5m bar (threshold 15min) - same age, two
    // different classifications, driven entirely by the timeframe.
    expect(classifyFreshness(minutesAgoIso(20), "1h", NOW)).toBe("current");
    expect(classifyFreshness(minutesAgoIso(20), "5m", NOW)).toBe("stale");
  });

  it("treats an unparseable timestamp as 'stale', never 'current', as a defensive default", () => {
    expect(classifyFreshness("not-a-timestamp", "5m", NOW)).toBe("stale");
  });

  it("treats a future timestamp (clock skew) as 'stale', never 'current'", () => {
    expect(classifyFreshness(new Date(NOW + 60_000).toISOString(), "5m", NOW)).toBe("stale");
  });
});
