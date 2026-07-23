"use client";

// Sprint 10 Slice F. Run Center - the operational control surface of the
// Research Engine, but strictly a dashboard: it explains what CAN be
// executed and shows current state, never executes anything itself. No
// POST, no workflow execution, no background jobs, no mutations, no
// replay/experiment launch, no action buttons (not even disabled ones -
// the kickoff is explicit that a disabled button is still a fake control).
//
// Zero new backend endpoints, zero new BFF allowlist entries, zero new
// typed-client functions - every read this page needs (/status,
// /research/leaderboard, /research/promotion/candidates) was already
// built and allowlisted by Slices B/E. This page is purely a new
// composition of three already-existing queries.
//
// The five-operation catalog (OPERATIONS below) is a frontend-declared
// constant, not fetched from any endpoint - there is no discovery API
// that reports "which research operations exist." This mirrors the
// existing PromotionDecisionValue precedent (a hardcoded literal union,
// not an enum-listing endpoint), and the catalog's own facts are pinned
// directly to the two backend source-of-truth constants it describes:
// atlas/api/v1/research_pipeline.py's `_RUN_MODES`/`_IMPLEMENTED_MODES`.
// Documented as a Slice G architectural note in the delivery report - if
// this catalog ever needs to grow independently of a person reading both
// files, a small `GET /research/operations` endpoint would remove the
// hand-maintained duplication, but today's catalog is small, stable, and
// this is not "absolutely unavoidable" per the kickoff's own bar.
//
// Sprint 10 Slice G: SectionLoading and the ledger-checks derivation
// (previously local to this page, byte-identical to the Overview page's
// own copies) are now shared - see components/ResearchOps/
// SectionLoading.tsx and lib/researchOpsLedgerChecks.ts's own comments.
// Run Center is the last stop in the workflow order the Slice G kickoff
// named, so it renders no NextStepLink of its own.

import { useQuery } from "@tanstack/react-query";
import { OperationAvailability, OperationCard } from "@/components/ResearchOps/OperationCard";
import { ReadinessCard } from "@/components/ResearchOps/ReadinessCard";
import { SectionLoading } from "@/components/ResearchOps/SectionLoading";
import { StatCard } from "@/components/ResearchOps/StatCard";
import { formatClockCT } from "@/lib/format";
import { buildLedgerChecks } from "@/lib/researchOpsLedgerChecks";
import {
  ApiFetchError,
  fetchLatestSnapshot,
  fetchOpsStatus,
  fetchPromotionCandidates,
} from "@/lib/researchOpsApi";

interface OperationDefinition {
  key: string;
  name: string;
  description: string;
  kind: "implemented" | "not_implemented" | "not_standalone";
  prerequisites: string[];
}

// Sourced from atlas/api/v1/research_pipeline.py: `_RUN_MODES = ("smoke",
// "replay", "experiment", "benchmark")`, `_IMPLEMENTED_MODES = ("smoke",)`.
// "Research Run" below is presented under its operator-facing name; the
// backend's own `mode="smoke"` is the currently-implemented case of it.
// "experiment" (a declared, unimplemented mode) is deliberately not its
// own catalog entry - the kickoff's own example list names Replay,
// Benchmark, Research Run, Validation, and Promotion Review, and
// "experiment" has no operator-facing identity distinct from a Research
// Run today; adding a sixth card for it would be presenting a Python
// literal as a product concept it isn't yet.
const OPERATIONS: OperationDefinition[] = [
  {
    key: "research-run",
    name: "Research Run",
    description: "Executes the research pipeline (mode=smoke) end-to-end against a self-contained synthetic dataset and persists every stage to the Ledger.",
    kind: "implemented",
    prerequisites: ["Research Ledger must be ready"],
  },
  {
    key: "replay",
    name: "Replay",
    description: "A declared run mode intended to replay a historical market window through the pipeline. Not yet built.",
    kind: "not_implemented",
    prerequisites: [],
  },
  {
    key: "benchmark",
    name: "Benchmark",
    description: "A declared run mode intended to benchmark realizations against a reference dataset. Not yet built.",
    kind: "not_implemented",
    prerequisites: [],
  },
  {
    key: "validation",
    name: "Validation",
    description: "Statistically validates a hypothesis's Evidence (walk-forward and Monte Carlo) and records a ValidationResult. Runs automatically as a stage inside a Research Run - not independently triggerable.",
    kind: "not_standalone",
    prerequisites: ["Evidence must already exist for the target hypothesis"],
  },
  {
    key: "promotion-review",
    name: "Promotion Review",
    description: "The human decision workflow that approves, declines, or defers a validated hypothesis. A review action, not a system operation - see the Promotion Queue and Promotion History pages.",
    kind: "not_standalone",
    prerequisites: ["A validated hypothesis with no APPROVED decision must exist in the latest snapshot"],
  },
];

export default function RunCenterPage() {
  const statusQuery = useQuery<Awaited<ReturnType<typeof fetchOpsStatus>>, ApiFetchError>({
    queryKey: ["research-ops-status"],
    queryFn: fetchOpsStatus,
  });
  const snapshotQuery = useQuery<Awaited<ReturnType<typeof fetchLatestSnapshot>>, ApiFetchError>({
    queryKey: ["research-ops-latest-snapshot"],
    queryFn: fetchLatestSnapshot,
  });
  const candidatesQuery = useQuery<Awaited<ReturnType<typeof fetchPromotionCandidates>>, ApiFetchError>({
    queryKey: ["research-ops-promotion-candidates"],
    queryFn: fetchPromotionCandidates,
  });

  const ledger = statusQuery.data?.research_ledger;
  const ledgerReady = ledger?.status === "ready";
  const ledgerChecks = buildLedgerChecks(ledger);

  const snapshotNotFound = snapshotQuery.isError && snapshotQuery.error.kind === "not_found";
  const snapshotDegraded = snapshotQuery.isError && !snapshotNotFound;

  // Availability per operation - see OperationCard's own comment for why
  // this is four states, not a binary. "Research Run" is the only
  // operation whose availability depends on live backend state
  // (statusQuery); the other four are fixed facts about the deployed API
  // surface, true regardless of whether /status has even resolved yet.
  function availabilityFor(op: OperationDefinition): { availability: OperationAvailability; detail: string | null } {
    if (op.kind === "not_implemented") {
      return { availability: "not_implemented", detail: "Declared as a run mode, but not yet implemented - the backend returns HTTP 501 for it unconditionally." };
    }
    if (op.kind === "not_standalone") {
      return { availability: "not_standalone", detail: null };
    }
    // kind === "implemented" (Research Run)
    if (statusQuery.isError) {
      return { availability: "unavailable", detail: "Backend unreachable." };
    }
    if (!statusQuery.data) {
      return { availability: "unavailable", detail: "Checking Research Ledger readiness…" };
    }
    if (!ledgerReady) {
      return { availability: "unavailable", detail: ledger?.reason ?? "Research Ledger is not ready." };
    }
    return { availability: "available", detail: null };
  }

  function stateFor(op: OperationDefinition): string {
    if (op.key === "research-run") {
      if (snapshotQuery.data) {
        return `Last observed output: snapshot ${snapshotQuery.data.snapshot_id} (${formatClockCT(snapshotQuery.data.created_at)}), ${snapshotQuery.data.entries.length} entr${snapshotQuery.data.entries.length === 1 ? "y" : "ies"} ranked.`;
      }
      if (snapshotNotFound) return "No leaderboard snapshot has been recorded yet - this operation has not produced output.";
      if (snapshotDegraded) return "Unable to determine - the Research Ledger is unreachable.";
      return "Checking for prior output…";
    }
    if (op.key === "validation") {
      if (snapshotQuery.data) {
        const validated = snapshotQuery.data.entries.filter((e) => e.validation_id !== null).length;
        return `${validated} of ${snapshotQuery.data.entries.length} entries in the latest snapshot carry a validation result.`;
      }
      if (snapshotNotFound) return "No leaderboard snapshot has been recorded yet.";
      if (snapshotDegraded) return "Unable to determine - the Research Ledger is unreachable.";
      return "Checking…";
    }
    if (op.key === "promotion-review") {
      if (candidatesQuery.data) {
        return `${candidatesQuery.data.candidates.length} candidate${candidatesQuery.data.candidates.length === 1 ? "" : "s"} currently awaiting review.`;
      }
      if (candidatesQuery.isError) return "Unable to determine - the Research Ledger is unreachable.";
      return "Checking…";
    }
    // replay / benchmark
    return "No prior executions - not yet implemented.";
  }

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-lg font-semibold text-foreground">Run Center</h1>
        <span className="text-xs text-muted">Research Engine operations - read-only</span>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {statusQuery.data || statusQuery.isError ? (
          <ReadinessCard
            title="Engine Status"
            status={statusQuery.isError ? "unreachable" : ledgerReady ? "ok" : "degraded"}
            statusLabel={statusQuery.isError ? "Backend Unreachable" : ledgerReady ? "Healthy" : "Degraded"}
            detail={statusQuery.isError ? statusQuery.error.message : ledger?.reason}
          />
        ) : (
          <SectionLoading title="Engine Status" />
        )}

        {statusQuery.data || statusQuery.isError ? (
          statusQuery.isError ? (
            <ReadinessCard title="Ledger Readiness" status="unreachable" statusLabel="Unavailable" detail={statusQuery.error.message} />
          ) : (
            <ReadinessCard
              title="Ledger Readiness"
              status={ledgerReady ? "ok" : "degraded"}
              statusLabel={ledgerReady ? "Ready" : "Degraded"}
              detail={ledger?.reason}
              checks={ledgerChecks}
            />
          )
        ) : (
          <SectionLoading title="Ledger Readiness" />
        )}

        {snapshotQuery.data ? (
          <StatCard label="Latest Snapshot" value={snapshotQuery.data.snapshot_id} detail={formatClockCT(snapshotQuery.data.created_at)} />
        ) : snapshotNotFound ? (
          <StatCard label="Latest Snapshot" value="" empty="No snapshot recorded yet." />
        ) : snapshotDegraded ? (
          <StatCard label="Latest Snapshot" value="" empty={snapshotQuery.error?.message ?? "Unavailable."} />
        ) : (
          <SectionLoading title="Latest Snapshot" />
        )}

        {statusQuery.data || statusQuery.isError ? (
          <StatCard
            label="Available Operations"
            value={String(OPERATIONS.filter((op) => availabilityFor(op).availability === "available").length)}
            detail={`of ${OPERATIONS.length} cataloged`}
          />
        ) : (
          <SectionLoading title="Available Operations" />
        )}
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {OPERATIONS.map((op) => {
          const { availability, detail } = availabilityFor(op);
          return (
            <OperationCard
              key={op.key}
              name={op.name}
              description={op.description}
              availability={availability}
              availabilityDetail={detail}
              prerequisites={op.prerequisites}
              state={stateFor(op)}
            />
          );
        })}
      </div>
    </section>
  );
}
