"use client";

// Sprint 10 Slice E. Promotion History - every recorded promotion decision,
// read-only. Answers "what decisions have already been made?" No editing,
// no re-decision, no POST - PromotionRecord is immutable by construction.
//
// Reuses fetchPromotionHistory() unchanged from Slice B/C (GET
// /research/promotion, already BFF-allowlisted) - the only new data-layer
// addition is reading the reviewer/rationale/evidence_snapshot_ref fields
// this slice adds to PromotionRecordSummary in researchOpsApi.ts. No new
// backend endpoint, no new BFF allowlist entry.
//
// Sprint 10 Slice G: SectionLoading/EmptyPanel (previously local to this
// page) are now shared - see components/ResearchOps/SectionLoading.tsx
// and EmptyPanel.tsx's own comments for why. Also adds this page's own
// NextStepLink to the Run Center, the final hop in the workflow order.

import { useQuery } from "@tanstack/react-query";
import { EmptyPanel } from "@/components/ResearchOps/EmptyPanel";
import { NextStepLink } from "@/components/ResearchOps/NextStepLink";
import { PromotionHistoryRow, PromotionHistoryTable } from "@/components/ResearchOps/PromotionHistoryTable";
import { SectionLoading } from "@/components/ResearchOps/SectionLoading";
import { StatCard } from "@/components/ResearchOps/StatCard";
import { ApiFetchError, fetchPromotionHistory } from "@/lib/researchOpsApi";

export default function PromotionHistoryPage() {
  const historyQuery = useQuery<Awaited<ReturnType<typeof fetchPromotionHistory>>, ApiFetchError>({
    queryKey: ["research-ops-promotion-history"],
    queryFn: fetchPromotionHistory,
  });

  const rows: PromotionHistoryRow[] = historyQuery.data
    ? historyQuery.data.records.map((record) => ({
        promotionId: record.promotion_id,
        hypothesisId: record.hypothesis_id,
        realizationId: record.realization_id,
        decision: record.decision,
        decidedAt: record.decided_at,
        rationale: record.rationale,
        evidenceSnapshotRef: record.evidence_snapshot_ref,
      }))
    : [];

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-lg font-semibold text-foreground">Promotion History</h1>
        <div className="flex items-center gap-3">
          <span className="text-xs text-muted">Research Engine operations - read-only</span>
          <NextStepLink href="/research-ops/run-center" label="Run Center" />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {historyQuery.data ? (
          <StatCard label="Total Decisions" value={String(historyQuery.data.records.length)} />
        ) : historyQuery.isError ? (
          <StatCard label="Total Decisions" value="" empty={historyQuery.error.message} />
        ) : (
          <SectionLoading title="Total Decisions" />
        )}

        {historyQuery.data ? (
          <StatCard
            label="Most Recent Decision"
            value={
              historyQuery.data.records.length === 0
                ? ""
                : historyQuery.data.records.reduce((a, b) => (a.decided_at > b.decided_at ? a : b)).hypothesis_id
            }
            empty={historyQuery.data.records.length === 0 ? "No decisions recorded yet." : null}
          />
        ) : historyQuery.isError ? (
          <StatCard label="Most Recent Decision" value="" empty="Unavailable." />
        ) : (
          <SectionLoading title="Most Recent Decision" />
        )}
      </div>

      {historyQuery.data ? (
        rows.length === 0 ? (
          <EmptyPanel message="No promotion decisions have been recorded yet." />
        ) : (
          <PromotionHistoryTable rows={rows} />
        )
      ) : historyQuery.isError ? (
        <EmptyPanel message={historyQuery.error.message} tone="error" />
      ) : (
        <EmptyPanel message="Loading…" />
      )}
    </section>
  );
}
