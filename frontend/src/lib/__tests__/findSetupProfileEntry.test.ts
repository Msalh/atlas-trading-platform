import { describe, expect, it } from "vitest";
import { findSetupProfileEntry } from "@/lib/researchApi";

function duration() {
  return { count: 5270, max: 10, mean: 1.48, median: 1, p75: 2, p90: 3, p95: 4 };
}

function report(entries: unknown[]) {
  return { setup_profile: { entries, manifest: {} } };
}

describe("findSetupProfileEntry", () => {
  it("finds the matching entry by setup_name", () => {
    const entry = {
      setup_name: "displacement_with_volume_confirmation",
      episode_count: 5270,
      all_episodes_duration: duration(),
      fully_observed_duration: duration(),
    };
    const result = findSetupProfileEntry(report([entry]), "displacement_with_volume_confirmation");
    expect(result).toEqual(entry);
  });

  it("returns null when no entry matches the setup name", () => {
    expect(findSetupProfileEntry(report([]), "displacement_with_volume_confirmation")).toBeNull();
  });

  it("returns null, never throws, on a malformed report", () => {
    expect(findSetupProfileEntry(null, "x")).toBeNull();
    expect(findSetupProfileEntry({}, "x")).toBeNull();
    expect(findSetupProfileEntry({ setup_profile: {} }, "x")).toBeNull();
    expect(findSetupProfileEntry({ setup_profile: { entries: "not-an-array" } }, "x")).toBeNull();
  });

  it("returns null when the matching entry is malformed", () => {
    const malformed = { setup_name: "x", episode_count: 1 }; // missing duration fields
    expect(findSetupProfileEntry(report([malformed]), "x")).toBeNull();
  });
});
