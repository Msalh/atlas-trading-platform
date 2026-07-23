"use client";

// Sprint 10 Slice B. Research Overview - observability only, per the
// approved Slice B scope: no editing, no workflow execution, no Promotion
// actions. Answers exactly the six questions the slice was scoped around:
// Research Engine healthy, Ledger healthy, latest Snapshot, latest
// Validation, how many Promotions exist, and one rolled-up overall status.
//
// Route is deliberately NOT /research - that path is already the frozen
// RE-1/RE-2 baseline page (a different backend subsystem entirely - see
// researchOpsApi.ts's own header comment). Resolving that naming collision
// in the shared nav is Slice G's own scope (navigation integration); this
// page is reachable by direct URL only until then, matching the approved
// delivery slices.
//
// Three independent queries, each with its own loading/error/empty state -
// never a single all-or-nothing page state, so one degraded signal never
// hides data the other two queries successfully returned.
//
// Sprint 10 Slice G: SectionLoading and the ledger-checks derivation
// (previously local to this page) are now shared - see
// components/ResearchOps/SectionLoading.tsx and
// lib/researchOpsLedgerChecks.ts's own comments for why. Also adds this
// page's own NextStepLink to Leaderboard, the first hop in the workflow
// order the Slice G kickoff named.

import { useQuery } from "@tanstack/react-query";
import { NextStepLink } from "@/components/ResearchOps/NextStepLink";
import { ReadinessCard } from "@/components/ResearchOps/ReadinessCard";
import { SectionLoading } from "@/components/ResearchOps/SectionLoading";
import { StatCard } from "@/components/ResearchOps/StatCard";
import { formatClockCT } from "@/lib/format";
import { buildLedgerChecks } from "@/lib/researchOpsLedgerChecks";
import {
  ApiFetchError,
  fetchLatestSnapshot,
  fetchOpsStatus,
  fetchPromotionHistory,
} from "@/lib/researchOpsApi";

export default function ResearchOpsOverviewPage() {
  const statusQuery = useQuery<Awaited<ReturnType<typeof fetchOpsStatus>>, ApiFetchError>({
    queryKey: ["research-ops-status"],
    queryFn: fetchOpsStatus,
  });
  const snapshotQuery = useQuery<Awaited<ReturnType<typeof fetchLatestSnapshot>>, ApiFetchError>({
    queryKey: ["research-ops-latest-snapshot"],
    queryFn: fetchLatestSnapshot,
  });
  const promotionsQuery = useQuery<Awaited<ReturnType<typeof fetchPromotionHistory>>, ApiFetchError>({
    queryKey: ["research-ops-promotion-history"],
    queryFn: fetchPromotionHistory,
  });

  const ledger = statusQuery.data?.research_ledger;
  const ledgerReady = ledger?.status === "ready";

  // ---- overall status: rolled up from the same /status call, never a
  //      second query - "is the Research Engine healthy" and "what is the
  //      current overall Research status" are the same underlying signal ----
  let overallStatus: "ok" | "degraded" | "unreachable" = "ok";
  let overallLabel = "Healthy";
  let overallDetail: string | null = null;
  if (statusQuery.isError) {
    overallStatus = "unreachable";
    overallLabel = "Backend Unreachable";
    overallDetail = statusQuery.error.message;
  } else if (statusQuery.data && !ledgerReady) {
    overallStatus = "degraded";
    overallLabel = "Degraded";
    overallDetail = ledger?.reason ?? "Research Ledger is not ready.";
  }

  const ledgerChecks = buildLedgerChecks(ledger);

  const latestEntry = snapshotQuery.data?.entries.find((e) => e.rank === 1) ?? null;
  const snapshotNotFound = snapshotQuery.isError && snapshotQuery.error.kind === "not_found";
  const snapshotDegraded = snapshotQuery.isError && !snapshotNotFound;

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-lg font-semibold text-foreground">Research Overview</h1>
        <div className="flex items-center gap-3">
          <span className="text-xs text-muted">Research Engine operations - read-only</span>
          <NextStepLink href="/research-ops/leaderboard" label="Leaderboard" />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {/* ---- Is the Research Engine healthy? / current overall status ----
             Gated on (data present OR a confirmed error), not isLoading -
             TanStack Query retries a failed query by default (query-
             provider.tsx sets no retry override), so there is a real,
             multi-second window after a failed fetch where isLoading is
             already false but isError has not yet been set either. Gating
             on isLoading alone rendered the "healthy"/successful branch
             during that window, showing stale-default content instead of
             an honest loading state - caught by live-browser verification
             against a real failing backend, not by the mocked-fetch unit
             tests (which resolve on the first attempt either way). */}
        {statusQuery.data || statusQuery.isError ? (
          <ReadinessCard title="Research Status" status={overallStatus} statusLabel={overallLabel} detail={overallDetail} />
        ) : (
          <SectionLoading title="Research Status" />
        )}

        {/* ---- Is the Ledger healthy? ---- */}
        {statusQuery.data || statusQuery.isError ? (
          statusQuery.isError ? (
            <ReadinessCard
              title="Ledger Readiness"
              status="unreachable"
              statusLabel="Unavailable"
              detail={statusQuery.error.message}
            />
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

        {/* ---- What is the latest Snapshot? ----
             Branches on `data` truthiness first, not isLoading/isError -
             TanStack Query has a real, if brief, render tick where a query
             has neither started fetching nor settled (isLoading and
             isError both false, data still undefined); branching on the
             boolean flags alone reached the "success" arm during that tick
             and crashed on `data!.snapshot_id` - caught by live-browser
             verification, not by the mocked-fetch unit tests, which never
             render that exact tick. Checking `data` directly avoids the
             non-null assertion entirely and is correct regardless of which
             flag combination TanStack Query happens to report. */}
        {snapshotQuery.data ? (
          <StatCard
            label="Latest Snapshot"
            value={snapshotQuery.data.snapshot_id}
            detail={`${snapshotQuery.data.entries.length} hypothes${snapshotQuery.data.entries.length === 1 ? "is" : "es"} ranked - as of ${formatClockCT(snapshotQuery.data.created_at)}`}
          />
        ) : snapshotNotFound ? (
          <StatCard label="Latest Snapshot" value="" empty="No snapshot recorded yet." />
        ) : snapshotDegraded ? (
          <StatCard label="Latest Snapshot" value="" empty={snapshotQuery.error?.message ?? "Unavailable."} />
        ) : (
          <SectionLoading title="Latest Snapshot" />
        )}

        {/* ---- What is the latest Validation? ---- */}
        {snapshotQuery.data ? (
          latestEntry ? (
            <StatCard
              label="Latest Validation"
              value={latestEntry.validation_id ?? "(no validation id)"}
              detail={`${latestEntry.hypothesis_id}${latestEntry.realization_id ? ` / ${latestEntry.realization_id}` : ""} - score ${latestEntry.score}`}
            />
          ) : (
            <StatCard label="Latest Validation" value="" empty="No validated hypothesis in the latest snapshot." />
          )
        ) : snapshotNotFound ? (
          <StatCard label="Latest Validation" value="" empty="No snapshot recorded yet." />
        ) : snapshotDegraded ? (
          <StatCard label="Latest Validation" value="" empty={snapshotQuery.error?.message ?? "Unavailable."} />
        ) : (
          <SectionLoading title="Latest Validation" />
        )}

        {/* ---- How many Promotions exist? ---- */}
        {promotionsQuery.data ? (
          promotionsQuery.data.records.length === 0 ? (
            <StatCard label="Promotions" value="" empty="No promotion decisions recorded yet." />
          ) : (
            <StatCard label="Promotions" value={String(promotionsQuery.data.records.length)} detail="total decisions recorded" />
          )
        ) : promotionsQuery.isError ? (
          <StatCard label="Promotions" value="" empty={promotionsQuery.error.message} />
        ) : (
          <SectionLoading title="Promotions" />
        )}
      </div>
    </section>
  );
}
