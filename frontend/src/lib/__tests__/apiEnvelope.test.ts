import { describe, expect, it } from "vitest";
import { isResponseEnvelope } from "@/lib/apiEnvelope";

function validEnvelope() {
  return {
    schema_version: "1.0",
    source_track: "live",
    symbol: "MNQU6",
    timeframe: "5m",
    generated_at: "2026-07-20T12:00:00Z",
    data_as_of: "2026-07-20T11:55:00Z",
    code_version: "abc123",
    warnings: [] as string[],
  };
}

describe("isResponseEnvelope", () => {
  it("accepts a well-formed live envelope", () => {
    expect(isResponseEnvelope(validEnvelope())).toBe(true);
  });

  it("accepts a well-formed frozen envelope with a null code_version", () => {
    expect(isResponseEnvelope({ ...validEnvelope(), source_track: "frozen", code_version: null })).toBe(true);
  });

  it("accepts non-empty warnings", () => {
    expect(isResponseEnvelope({ ...validEnvelope(), warnings: ["window truncated"] })).toBe(true);
  });

  it("rejects a source_track outside the closed live/frozen set", () => {
    expect(isResponseEnvelope({ ...validEnvelope(), source_track: "cached" })).toBe(false);
  });

  it("rejects a missing field", () => {
    const envelope: Record<string, unknown> = validEnvelope();
    delete envelope.data_as_of;
    expect(isResponseEnvelope(envelope)).toBe(false);
  });

  it("rejects warnings containing a non-string entry", () => {
    expect(isResponseEnvelope({ ...validEnvelope(), warnings: [1, 2] })).toBe(false);
  });

  it("rejects null and non-object input", () => {
    expect(isResponseEnvelope(null)).toBe(false);
    expect(isResponseEnvelope("envelope")).toBe(false);
    expect(isResponseEnvelope(undefined)).toBe(false);
  });
});
