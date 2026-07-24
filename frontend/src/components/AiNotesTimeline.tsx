"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { fetchAiNotes } from "@/lib/aiApi";
import { formatClock } from "@/lib/format";
import { pollInterval } from "@/lib/intervals";
import { useLiveUpdatesConnected } from "@/lib/live-updates";

const TYPE_LABEL: Record<string, string> = {
  entry_score: "Entry Score",
  post_trade_review: "Post-Trade Review",
};

export function AiNotesTimeline() {
  const sseConnected = useLiveUpdatesConnected();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["ai", "notes", "timeline"],
    queryFn: () => fetchAiNotes({ limit: 30 }),
    refetchInterval: pollInterval(sseConnected, 10_000),
  });

  const notes = data?.notes.filter((n) => n.note_type === "entry_score" || n.note_type === "post_trade_review") ?? [];

  return (
    <section className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-3 text-sm font-semibold text-muted uppercase tracking-wide">AI Notes Timeline</h2>

      {isLoading && <p className="text-sm text-muted">Loading…</p>}
      {isError && <p className="text-sm text-danger">Could not load AI notes.</p>}
      {data && notes.length === 0 && (
        <p className="py-8 text-center text-sm text-muted">No AI notes yet.</p>
      )}

      {notes.length > 0 && (
        <ol className="divide-y divide-border">
          {notes.map((note) => (
            <li key={note.id} className="py-3">
              <div className="mb-1 flex items-center justify-between text-xs text-muted">
                <span className="font-medium text-foreground">
                  {TYPE_LABEL[note.note_type] ?? note.note_type}
                  {note.note_type === "entry_score" && note.score !== null && (
                    <span className="ml-2 text-muted">{note.score}/10{note.score_label ? ` · ${note.score_label}` : ""}</span>
                  )}
                </span>
                <span>{formatClock(note.created_at)}</span>
              </div>
              <p className={`text-sm ${note.error ? "text-danger" : ""}`}>
                {note.error ? `Failed: ${note.error}` : note.content}
              </p>
              {note.trade_correlation_id && (
                <Link
                  href={`/trades/${encodeURIComponent(note.trade_correlation_id)}`}
                  className="mt-1 inline-block text-xs text-open hover:underline"
                >
                  view trade →
                </Link>
              )}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
