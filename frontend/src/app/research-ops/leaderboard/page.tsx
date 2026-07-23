"use client";

// Sprint 10 Slice C. Leaderboard - the latest LeaderboardSnapshot's ranked
// entries, read-only. Answers: which hypotheses currently rank highest,
// what snapshot produced these rankings, how many entries exist, and the
// key metrics for each. No Snapshot Explorer, no Lineage Viewer, no
// Promotion actions, no filtering/sorting/pagination/export/search - all
// explicitly deferred to later slices.
//
// Reuses fetchLatestSnapshot/fetchPromotionHistory unchanged from Slice B's
// researchOpsApi.ts - no new backend endpoint, no new BFF allowlist entry
// (both paths were already registered in Slice B). The only new data-layer
// addition is deriveEntryPromotionStatus(), a pure client-side join over
// data both queries already fetch.
//
// State branching follows the exact discipline Slice B's own live-browser
// verification forced: gate on `data` presence (or a confirmed error),
// never on isLoading/isError flags alone - see researchOpsApi.ts and the
// Overview page for the full reasoning.
//
// Sprint 10 Slice G: SectionLoading/EmptyPanel (previously local to this
// page) are now shared - see components/ResearchOps/SectionLoading.tsx
// and EmptyPanel.tsx's own comments for why. Also adds this page's own
// NextStepLink to Snapshot Explorer, the next hop in the workflow order.

import { useQuery } from "@tanstack/react-query";
import { EmptyPanel } from "@/components/ResearchOps/EmptyPanel";
import { LeaderboardRow, LeaderboardTable } from "@/components/ResearchOps/LeaderboardTable";
import { NextStepLink } from "@/components/ResearchOps/NextStepLink";
import { SectionLoading } from "@/components/ResearchOps/SectionLoading";
import { StatCard } from "@/components/ResearchOps/StatCard";
import { formatClockCT } from "@/lib/format";
import {
  ApiFetchError,
  deriveEntryPromotionStatus,
  fetchLatestSnapshot,
  fetchPromotionHistory,
} from "@/lib/researchOpsApi";

export default function LeaderboardPage() {
  const snapshotQuery = useQuery<Awaited<ReturnType<typeof fetchLatestSnapshot>>, ApiFetchError>({
    queryKey: ["research-ops-latest-snapshot"],
    queryFn: fetchLatestSnapshot,
  });
  const promotionsQuery = useQuery<Awaited<ReturnType<typeof fetchPromotionHistory>>, ApiFetchError>({
    queryKey: ["research-ops-promotion-history"],
    queryFn: fetchPromotionHistory,
  });

  const snapshotNotFound = snapshotQuery.isError && snapshotQuery.error.kind === "not_found";
  const snapshotDegraded = snapshotQuery.isError && !snapshotNotFound;

  const rows: LeaderboardRow[] = snapshotQuery.data
    ? snapshotQuery.data.entries.map((entry) => ({
        rank: entry.rank,
        hypothesisId: entry.hypothesis_id,
        realizationId: entry.realization_id,
        score: entry.score,
        validationId: entry.validation_id,
        status: deriveEntryPromotionStatus(entry, promotionsQuery.data?.records ?? []),
      }))
    : [];

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-lg font-semibold text-foreground">Leaderboard</h1>
        <div className="flex items-center gap-3">
          <span className="text-xs text-muted">Research Engine operations - read-only</span>
          <NextStepLink href="/research-ops/snapshot" label="Snapshot Explorer" />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {snapshotQuery.data ? (
          <StatCard label="Snapshot ID" value={snapshotQuery.data.snapshot_id} />
        ) : snapshotNotFound ? (
          <StatCard label="Snapshot ID" value="" empty="No snapshot recorded yet." />
        ) : snapshotDegraded ? (
          <StatCard label="Snapshot ID" value="" empty={snapshotQuery.error?.message ?? "Unavailable."} />
        ) : (
          <SectionLoading title="Snapshot ID" />
        )}

        {snapshotQuery.data ? (
          <StatCard label="Total Ranked Hypotheses" value={String(snapshotQuery.data.entries.length)} />
        ) : snapshotNotFound || snapshotDegraded ? (
          <StatCard label="Total Ranked Hypotheses" value="" empty="Unavailable." />
        ) : (
          <SectionLoading title="Total Ranked Hypotheses" />
        )}

        {snapshotQuery.data ? (
          <StatCard label="Snapshot Timestamp" value={formatClockCT(snapshotQuery.data.created_at)} />
        ) : snapshotNotFound || snapshotDegraded ? (
          <StatCard label="Snapshot Timestamp" value="" empty="Unavailable." />
        ) : (
          <SectionLoading title="Snapshot Timestamp" />
        )}

        {promotionsQuery.data ? (
          <StatCard label="Promotions" value={String(promotionsQuery.data.records.length)} detail="total decisions recorded" />
        ) : promotionsQuery.isError ? (
          <StatCard label="Promotions" value="" empty={promotionsQuery.error.message} />
        ) : (
          <SectionLoading title="Promotions" />
        )}
      </div>

      {snapshotQuery.data ? (
        rows.length === 0 ? (
          <EmptyPanel message="The latest snapshot has no ranked hypotheses." />
        ) : (
          <LeaderboardTable rows={rows} />
        )
      ) : snapshotNotFound ? (
        <EmptyPanel message="No snapshot has been recorded yet." />
      ) : snapshotDegraded ? (
        <EmptyPanel message={snapshotQuery.error?.message ?? "Unavailable."} tone="error" />
      ) : (
        <EmptyPanel message="Loading…" />
      )}
    </section>
  );
}
