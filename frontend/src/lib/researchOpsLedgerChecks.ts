// Sprint 10 Slice G (consistency consolidation). Extracted from two
// identical local copies (Overview's Ledger Readiness card, Run Center's
// Ledger Readiness card both built the exact same LEDGER_CHECK_ORDER/
// LEDGER_CHECK_LABELS constants and the exact same
// ResearchLedgerReadiness -> ReadinessCheck[] mapping). Pure - takes the
// already-fetched OpsStatusResponse's own research_ledger field, returns
// nothing a caller couldn't compute itself; exists only to stop a third
// page from re-typing the same five check names and labels.

import { ReadinessCheck } from "@/components/ResearchOps/ReadinessCard";
import { ResearchLedgerReadiness } from "@/lib/researchOpsApi";

const LEDGER_CHECK_ORDER = [
  "configuration_valid",
  "ledger_directory",
  "volume_mounted",
  "jsonl_stores_initialized",
  "registries_available",
] as const;

const LEDGER_CHECK_LABELS: Record<string, string> = {
  configuration_valid: "Configuration valid",
  ledger_directory: "Ledger directory",
  volume_mounted: "Volume mounted",
  jsonl_stores_initialized: "JSONL stores initialized",
  registries_available: "Registries available",
};

export function buildLedgerChecks(ledger: ResearchLedgerReadiness | undefined): ReadinessCheck[] | undefined {
  if (!ledger) return undefined;
  return LEDGER_CHECK_ORDER.map((name) => ({
    label: LEDGER_CHECK_LABELS[name],
    ok: ledger.checks[name]?.ok ?? false,
    detail: ledger.checks[name]?.detail ?? undefined,
  }));
}
