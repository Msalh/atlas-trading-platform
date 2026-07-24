"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { fetchAiReports, triggerReport, type ReportPeriod } from "@/lib/aiApi";
import { formatClock } from "@/lib/format";
import { pollInterval } from "@/lib/intervals";
import { useLiveUpdatesConnected } from "@/lib/live-updates";

export function AiReportsPanel() {
  const sseConnected = useLiveUpdatesConnected();
  const queryClient = useQueryClient();
  const [justTriggered, setJustTriggered] = useState<ReportPeriod | null>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["ai", "reports"],
    queryFn: () => fetchAiReports({ limit: 10 }),
    refetchInterval: pollInterval(sseConnected, 10_000),
  });

  const trigger = useMutation({
    mutationFn: triggerReport,
    onSuccess: (_data, period) => {
      setJustTriggered(period);
      // Generation happens in a background task on the server - refetch shortly
      // after to pick it up without the user having to manually refresh. This is a
      // one-shot delayed refetch, not a poll loop - the regular refetchInterval
      // above already covers ongoing updates.
      setTimeout(() => queryClient.invalidateQueries({ queryKey: ["ai", "reports"] }), 4_000);
    },
  });

  return (
    <section className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-muted uppercase tracking-wide">Reports</h2>
        <div className="flex gap-2">
          <button
            onClick={() => trigger.mutate("daily")}
            disabled={trigger.isPending}
            className="rounded border border-border px-2 py-1 text-xs text-muted hover:bg-surface-raised disabled:opacity-50"
          >
            Generate daily
          </button>
          <button
            onClick={() => trigger.mutate("weekly")}
            disabled={trigger.isPending}
            className="rounded border border-border px-2 py-1 text-xs text-muted hover:bg-surface-raised disabled:opacity-50"
          >
            Generate weekly
          </button>
        </div>
      </div>

      {justTriggered && (
        <p className="mb-3 rounded-md border border-open/30 bg-open/10 px-3 py-2 text-xs text-open">
          Generating {justTriggered} report in the background - it will appear below shortly.
        </p>
      )}

      {isLoading && <p className="text-sm text-muted">Loading…</p>}
      {isError && <p className="text-sm text-danger">Could not load reports.</p>}
      {data && data.reports.length === 0 && (
        <p className="py-6 text-center text-sm text-muted">No reports generated yet.</p>
      )}

      {data && data.reports.length > 0 && (
        <ol className="space-y-4">
          {data.reports.map((report) => (
            <li key={report.id} className="rounded-md bg-surface-raised p-3">
              <div className="mb-1 flex items-center justify-between text-xs text-muted">
                <span className="font-medium text-foreground uppercase">
                  {report.note_type.replace("_report", "")}
                </span>
                <span>{formatClock(report.created_at)}</span>
              </div>
              <p className={`text-sm ${report.error ? "text-danger" : ""}`}>
                {report.error ? `Failed: ${report.error}` : report.content}
              </p>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
