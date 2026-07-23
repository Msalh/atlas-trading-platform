// Sprint 10 Slice E. Promotion History table - read-only, no
// filtering/sorting/pagination/export/search. Rows are the complete
// PromotionRecord history from GET /research/promotion, already fetched
// unchanged since Slice B/C - this slice only adds the reviewer/rationale/
// evidence_snapshot_ref fields to the existing typed client (see
// researchOpsApi.ts) and renders them here for the first time.

import { PromotionDecisionValue } from "@/lib/researchOpsApi";
import { PromotionStatusBadge } from "@/components/ResearchOps/PromotionStatusBadge";
import { formatClockCT } from "@/lib/format";

export interface PromotionHistoryRow {
  promotionId: string;
  hypothesisId: string;
  realizationId: string | null;
  decision: PromotionDecisionValue;
  decidedAt: string;
  rationale: string;
  evidenceSnapshotRef: string;
}

export function PromotionHistoryTable({ rows }: { rows: PromotionHistoryRow[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-border bg-surface">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-border text-xs uppercase tracking-wide text-muted">
            <th className="px-4 py-2 font-semibold">Hypothesis</th>
            <th className="px-4 py-2 font-semibold">Decision</th>
            <th className="px-4 py-2 font-semibold">Decided</th>
            <th className="px-4 py-2 font-semibold">Reason</th>
            <th className="px-4 py-2 font-semibold">Snapshot Reference</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {rows.map((row) => (
            <tr key={row.promotionId}>
              <td className="px-4 py-2">
                <div className="font-mono text-foreground">{row.hypothesisId}</div>
                {row.realizationId && <div className="font-mono text-xs text-muted">{row.realizationId}</div>}
              </td>
              <td className="px-4 py-2">
                <PromotionStatusBadge status={row.decision} />
              </td>
              <td className="px-4 py-2 text-xs text-muted">{formatClockCT(row.decidedAt)}</td>
              <td className="px-4 py-2 text-xs text-foreground">{row.rationale}</td>
              <td className="px-4 py-2 font-mono text-xs text-muted">{row.evidenceSnapshotRef}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
