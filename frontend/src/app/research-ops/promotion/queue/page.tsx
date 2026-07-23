"use client";

// Sprint 10 Slice E. Promotion Queue - every realization currently
// awaiting review, read-only. Answers "what still requires review?" No
// Approve/Reject/Defer actions here - those remain out of scope until the
// review workflow itself has been reviewed (a later slice).
//
// Reuses GET /research/promotion/candidates (atlas/api/v1/promotion.py,
// built in Sprint 9) unchanged - list_promotion_candidates() already
// excludes anything with an APPROVED decision for its own (hypothesis_id,
// realization_id) pair, so this endpoint's own response IS the queue, no
// client-side filtering needed. fetchLatestSnapshot() (Slice B) is reused
// only to surface the snapshot's created_at timestamp, which the
// candidates endpoint itself doesn't carry - no new backend endpoint, just
// a second already-existing, already-allowlisted read.
//
// Sprint 10 Slice E.1 (hardening, per the certification review's own
// semantic analysis): candidatesQuery and snapshotQuery are two
// independent HTTP requests with no atomicity guarantee across them - if a
// new LeaderboardSnapshot is written in the (small) window between the
// two reads, they can legitimately resolve to two different snapshots.
// Both endpoints select "latest" via the identical `max(.., key=created_at)`
// (see atlas/api/v1/promotion.py's read_promotion_candidates and
// atlas/api/v1/research_pipeline.py's read_leaderboard), so this is not
// hypothetical, just narrow. The timestamp is therefore shown only after
// explicit reconciliation - snapshotIdsMatch below - never paired blind.
// The per-row Timestamp column that used to synthesize this same
// unreconciled value onto every candidate has been removed entirely (see
// PromotionQueueTable's own comment) - the verified value now lives only
// in this page's own summary strip.
//
// State branching follows the same "gate on data presence, not
// isLoading/isError" discipline every ResearchOps page has used since
// Slice B's own live-verification findings.
//
// Sprint 10 Slice G: SectionLoading/EmptyPanel (previously local to this
// page) are now shared - see components/ResearchOps/SectionLoading.tsx
// and EmptyPanel.tsx's own comments for why. Also adds this page's own
// NextStepLink to Promotion History, the next hop in the workflow order.

import { useQuery } from "@tanstack/react-query";
import { EmptyPanel } from "@/components/ResearchOps/EmptyPanel";
import { NextStepLink } from "@/components/ResearchOps/NextStepLink";
import { PromotionQueueRow, PromotionQueueTable } from "@/components/ResearchOps/PromotionQueueTable";
import { SectionLoading } from "@/components/ResearchOps/SectionLoading";
import { StatCard } from "@/components/ResearchOps/StatCard";
import { formatClockCT } from "@/lib/format";
import { ApiFetchError, deriveCandidateStatus, fetchLatestSnapshot, fetchPromotionCandidates } from "@/lib/researchOpsApi";

export default function PromotionQueuePage() {
  const candidatesQuery = useQuery<Awaited<ReturnType<typeof fetchPromotionCandidates>>, ApiFetchError>({
    queryKey: ["research-ops-promotion-candidates"],
    queryFn: fetchPromotionCandidates,
  });
  const snapshotQuery = useQuery<Awaited<ReturnType<typeof fetchLatestSnapshot>>, ApiFetchError>({
    queryKey: ["research-ops-latest-snapshot"],
    queryFn: fetchLatestSnapshot,
  });

  const rows: PromotionQueueRow[] = candidatesQuery.data
    ? candidatesQuery.data.candidates.map((candidate) => ({
        hypothesisId: candidate.hypothesis_id,
        realizationId: candidate.realization_id,
        validationId: candidate.validation_id,
        score: candidate.score,
        status: deriveCandidateStatus(candidate),
        snapshotId: candidatesQuery.data!.snapshot_id ?? "",
      }))
    : [];

  // Both queries must have settled (data or error) before the timestamp
  // card can render anything but Loading - and even then, the timestamp
  // itself only renders when both resolved to the exact same snapshot_id.
  const bothSettled = (candidatesQuery.data !== undefined || candidatesQuery.isError) && (snapshotQuery.data !== undefined || snapshotQuery.isError);
  const snapshotIdsMatch =
    candidatesQuery.data?.snapshot_id != null &&
    snapshotQuery.data?.snapshot_id != null &&
    candidatesQuery.data.snapshot_id === snapshotQuery.data.snapshot_id;

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-lg font-semibold text-foreground">Promotion Queue</h1>
        <div className="flex items-center gap-3">
          <span className="text-xs text-muted">Research Engine operations - read-only</span>
          <NextStepLink href="/research-ops/promotion/history" label="Promotion History" />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {candidatesQuery.data ? (
          <StatCard label="Snapshot ID" value={candidatesQuery.data.snapshot_id ?? ""} empty={candidatesQuery.data.snapshot_id ? null : "No snapshot recorded yet."} />
        ) : candidatesQuery.isError ? (
          <StatCard label="Snapshot ID" value="" empty={candidatesQuery.error.message} />
        ) : (
          <SectionLoading title="Snapshot ID" />
        )}

        {bothSettled ? (
          snapshotIdsMatch && snapshotQuery.data ? (
            <StatCard label="Snapshot Timestamp" value={formatClockCT(snapshotQuery.data.created_at)} />
          ) : (
            <StatCard label="Snapshot Timestamp" value="" empty="Unavailable." />
          )
        ) : (
          <SectionLoading title="Snapshot Timestamp" />
        )}

        {candidatesQuery.data ? (
          <StatCard label="Awaiting Review" value={String(candidatesQuery.data.candidates.length)} />
        ) : candidatesQuery.isError ? (
          <StatCard label="Awaiting Review" value="" empty="Unavailable." />
        ) : (
          <SectionLoading title="Awaiting Review" />
        )}
      </div>

      {candidatesQuery.data ? (
        candidatesQuery.data.snapshot_id === null ? (
          <EmptyPanel message="No snapshot has been recorded yet." />
        ) : rows.length === 0 ? (
          <EmptyPanel message="No candidates are currently awaiting review." />
        ) : (
          <PromotionQueueTable rows={rows} />
        )
      ) : candidatesQuery.isError ? (
        <EmptyPanel message={candidatesQuery.error.message} tone="error" />
      ) : (
        <EmptyPanel message="Loading…" />
      )}
    </section>
  );
}
