"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchAiNotes } from "@/lib/aiApi";
import { pollInterval } from "@/lib/intervals";
import { useLiveUpdatesConnected } from "@/lib/live-updates";

// Sprint 7: labels come from atlas/intelligence.py::compute_confidence's fixed rubric,
// not from Claude - see that module's docstring for why "Insufficient History" can
// appear even alongside a computed numeric score (a thin sample still gets a score,
// just flagged as not trustworthy yet).
const LABEL_COLOR: Record<string, string> = {
  "High Confidence": "text-long border-long/30 bg-long/10",
  "Moderate Confidence": "text-open border-open/30 bg-open/10",
  "Low Confidence": "text-warn border-warn/30 bg-warn/10",
  "Insufficient History": "text-muted border-border bg-surface-raised",
};

export function EntryScoreBadge({ correlationId }: { correlationId: string }) {
  const sseConnected = useLiveUpdatesConnected();
  const { data } = useQuery({
    queryKey: ["ai", "notes", correlationId, "entry_score"],
    queryFn: () => fetchAiNotes({ tradeCorrelationId: correlationId, noteType: "entry_score", limit: 1 }),
    refetchInterval: pollInterval(sseConnected, 5_000),
  });

  const note = data?.notes[0];
  if (!note) {
    return <span className="text-xs text-muted">scoring…</span>;
  }

  const tooltip = [
    note.content,
    note.similar_trade_count !== null ? `${note.similar_trade_count} similar historical trade(s)` : null,
    note.error,
  ]
    .filter(Boolean)
    .join(" — ");

  if (note.score === null) {
    return (
      <span
        className="rounded-full border border-border bg-surface-raised px-2 py-0.5 text-[11px] font-semibold text-muted"
        title={tooltip || undefined}
      >
        Insufficient History
      </span>
    );
  }

  const colorClass = (note.score_label && LABEL_COLOR[note.score_label]) || "text-muted border-border bg-surface-raised";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold ${colorClass}`}
      title={tooltip || undefined}
    >
      AI {note.score}/10{note.score_label ? ` · ${note.score_label}` : ""}
    </span>
  );
}
