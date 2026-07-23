import { describe, expect, it } from "vitest";
import { buildLedgerChecks } from "@/lib/researchOpsLedgerChecks";
import { ResearchLedgerReadiness } from "@/lib/researchOpsApi";

describe("buildLedgerChecks", () => {
  it("returns undefined when no ledger readiness is given", () => {
    expect(buildLedgerChecks(undefined)).toBeUndefined();
  });

  it("maps all five known checks in a fixed order, with labels", () => {
    const ledger: ResearchLedgerReadiness = {
      status: "ready",
      reason: null,
      checks: {
        configuration_valid: { ok: true, reason: null, detail: null },
        ledger_directory: { ok: true, reason: null, detail: null },
        volume_mounted: { ok: true, reason: null, detail: null },
        jsonl_stores_initialized: { ok: true, reason: null, detail: null },
        registries_available: { ok: true, reason: null, detail: null },
      },
    };
    const checks = buildLedgerChecks(ledger);
    expect(checks).toHaveLength(5);
    expect(checks?.map((c) => c.label)).toEqual([
      "Configuration valid",
      "Ledger directory",
      "Volume mounted",
      "JSONL stores initialized",
      "Registries available",
    ]);
    expect(checks?.every((c) => c.ok)).toBe(true);
  });

  it("defaults a missing check to not-ok, not a crash", () => {
    const ledger: ResearchLedgerReadiness = {
      status: "degraded",
      reason: "research_ledger_not_configured",
      checks: {
        configuration_valid: { ok: false, reason: "research_ledger_not_configured", detail: "RESEARCH_LEDGER_DIR is not set" },
      },
    };
    const checks = buildLedgerChecks(ledger);
    const configCheck = checks?.find((c) => c.label === "Configuration valid");
    expect(configCheck).toMatchObject({ ok: false, detail: "RESEARCH_LEDGER_DIR is not set" });
    const missingCheck = checks?.find((c) => c.label === "Ledger directory");
    expect(missingCheck).toMatchObject({ ok: false });
  });
});
