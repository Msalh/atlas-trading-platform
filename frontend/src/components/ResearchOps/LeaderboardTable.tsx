// Sprint 10 Slice C. A clean, minimal leaderboard table - read-only, no
// sorting/filtering/pagination/export/search (all explicitly out of this
// slice's scope; the rows are always the complete, already-ranked entry
// list of one snapshot, so there is nothing to page through). Rank/Score/
// Validation come straight off the backend's own LeaderboardEntry; Status
// is derived client-side (see researchOpsApi.ts's deriveEntryPromotionStatus)
// from data already fetched for the page's own summary strip - never a
// new query, never a link to a page that doesn't exist yet (Snapshot
// Explorer is Slice D's own scope).

import { EntryPromotionStatus } from "@/lib/researchOpsApi";
import { PromotionStatusBadge } from "@/components/ResearchOps/PromotionStatusBadge";

export interface LeaderboardRow {
  rank: number;
  hypothesisId: string;
  realizationId: string | null;
  score: number;
  validationId: string | null;
  status: EntryPromotionStatus;
}

export function LeaderboardTable({ rows }: { rows: LeaderboardRow[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-border bg-surface">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-border text-xs uppercase tracking-wide text-muted">
            <th className="px-4 py-2 font-semibold">Rank</th>
            <th className="px-4 py-2 font-semibold">Hypothesis</th>
            <th className="px-4 py-2 font-semibold">Score</th>
            <th className="px-4 py-2 font-semibold">Validation</th>
            <th className="px-4 py-2 font-semibold">Status</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {rows.map((row) => (
            <tr key={`${row.hypothesisId}-${row.realizationId ?? "none"}`}>
              <td className="px-4 py-2 font-mono text-foreground">{row.rank}</td>
              <td className="px-4 py-2">
                <div className="font-mono text-foreground">{row.hypothesisId}</div>
                {row.realizationId && <div className="font-mono text-xs text-muted">{row.realizationId}</div>}
              </td>
              <td className="px-4 py-2 font-mono text-foreground">{row.score}</td>
              <td className="px-4 py-2 font-mono text-xs text-muted">{row.validationId ?? "—"}</td>
              <td className="px-4 py-2">
                <PromotionStatusBadge status={row.status} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
