import { describe, expect, it } from "vitest";
import { formatClockCT, formatDateShortCT } from "@/lib/format";

// Production-hardening amendment 4. Jan and Jul are always safely on one
// side of the US DST boundary (second Sunday in March -> first Sunday in
// November) regardless of year, so these two instants exercise CST
// (UTC-6) and CDT (UTC-5) without depending on the exact transition date.
const CST_INSTANT = "2026-01-15T18:00:00Z"; // -> 12:00:00 PM CT (UTC-6)
const CDT_INSTANT = "2026-07-15T18:00:00Z"; // -> 01:00:00 PM CT (UTC-5)

describe("formatClockCT", () => {
  it("converts a CST (winter) UTC instant to the correct Central time and labels it CT", () => {
    expect(formatClockCT(CST_INSTANT)).toBe("Jan 15, 12:00:00 PM CT");
  });

  it("converts a CDT (summer) UTC instant to the correct Central time and labels it CT", () => {
    expect(formatClockCT(CDT_INSTANT)).toBe("Jul 15, 01:00:00 PM CT");
  });

  it("applies the same 1-hour DST shift automatically, with no manual offset logic", () => {
    // Same wall-clock UTC hour (18:00) on both dates - the only reason the
    // rendered CT hour differs (12 PM vs 1 PM) is the runtime's own IANA
    // timezone database applying CST vs CDT for each instant.
    const cst = formatClockCT(CST_INSTANT);
    const cdt = formatClockCT(CDT_INSTANT);
    expect(cst).toContain("12:00:00 PM");
    expect(cdt).toContain("01:00:00 PM");
  });

  it("returns a placeholder for null/undefined without throwing", () => {
    expect(formatClockCT(null)).toBe("-");
    expect(formatClockCT(undefined)).toBe("-");
  });

  it("falls back to the raw string for an unparseable value", () => {
    expect(formatClockCT("not-a-date")).toBe("not-a-date");
  });
});

describe("formatDateShortCT", () => {
  it("renders a CT-labeled short date for a CST instant", () => {
    expect(formatDateShortCT(CST_INSTANT)).toBe("Jan 15 CT");
  });

  it("renders a CT-labeled short date for a CDT instant", () => {
    expect(formatDateShortCT(CDT_INSTANT)).toBe("Jul 15 CT");
  });

  it("a UTC late-night timestamp can land on the previous CT calendar day", () => {
    // 2026-01-01T05:00:00Z is Jan 1 in UTC but still Dec 31 in CT (UTC-6) -
    // proves the date conversion is timezone-aware, not just the clock.
    expect(formatDateShortCT("2026-01-01T05:00:00Z")).toBe("Dec 31 CT");
  });
});
