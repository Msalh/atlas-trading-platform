// Sprint 10 Slice E. Promotion Queue table - read-only, no
// filtering/sorting/pagination/export/search (all out of this slice's
// scope; rows are always the complete candidate list the backend's own
// list_promotion_candidates() already returns for the single latest
// snapshot - there is nothing to page through). No Approve/Reject/Defer
// actions - those are a future slice's own scope, after the workflow
// itself is reviewed.
//
// Sprint 10 Slice E.1: the per-row Timestamp column removed. The
// candidates endpoint (GET /research/promotion/candidates) never returns
// a timestamp of its own - the value populating that column was always
// the *separately-fetched* latest-snapshot's created_at, applied
// identically to every row regardless of whether it actually matched that
// row's own Snapshot ID. Since the two reads are independent HTTP
// requests with no atomicity guarantee across them, that pairing could
// silently show a newer snapshot's timestamp next to an older snapshot's
// candidates. The verified (snapshot_id-reconciled) timestamp now lives
// only in the page's own summary strip - see page.tsx.
//
// Sprint 10 Slice E.1: a "declined" status renders as "Previously
// Declined" here (via PromotionStatusBadge's `label` override) - see that
// component's own comment for why. deriveCandidateStatus() itself is
// unchanged; this is presentation-only, scoped to this table alone.

import { EntryPromotionStatus } from "@/lib/researchOpsApi";
import { PromotionStatusBadge } from "@/components/ResearchOps/PromotionStatusBadge";

export interface PromotionQueueRow {
  hypothesisId: string;
  realizationId: string | null;
  validationId: string | null;
  score: number;
  status: EntryPromotionStatus;
  snapshotId: string;
}

export function PromotionQueueTable({ rows }: { rows: PromotionQueueRow[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-border bg-surface">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-border text-xs uppercase tracking-wide text-muted">
            <th className="px-4 py-2 font-semibold">Hypothesis</th>
            <th className="px-4 py-2 font-semibold">Validation</th>
            <th className="px-4 py-2 font-semibold">Score</th>
            <th className="px-4 py-2 font-semibold">Status</th>
            <th className="px-4 py-2 font-semibold">Snapshot</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {rows.map((row) => (
            <tr key={`${row.hypothesisId}-${row.realizationId ?? "none"}`}>
              <td className="px-4 py-2">
                <div className="font-mono text-foreground">{row.hypothesisId}</div>
                {row.realizationId && <div className="font-mono text-xs text-muted">{row.realizationId}</div>}
              </td>
              <td className="px-4 py-2 font-mono text-xs text-muted">{row.validationId ?? "—"}</td>
              <td className="px-4 py-2 font-mono text-foreground">{row.score}</td>
              <td className="px-4 py-2">
                <PromotionStatusBadge status={row.status} label={row.status === "declined" ? "Previously Declined" : undefined} />
              </td>
              <td className="px-4 py-2 font-mono text-xs text-muted">{row.snapshotId}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
