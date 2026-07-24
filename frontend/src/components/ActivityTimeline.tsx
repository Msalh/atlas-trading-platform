"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { ActivityCategory, ActivityEvent, ActivitySeverity, fetchActivity } from "@/lib/activityApi";
import { formatClock } from "@/lib/format";
import { pollInterval } from "@/lib/intervals";
import { useLiveUpdatesConnected } from "@/lib/live-updates";

type Filter = "all" | ActivityCategory | "critical";

const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "trading", label: "Trading" },
  { key: "ai", label: "AI" },
  { key: "risk", label: "Risk" },
  { key: "analytics", label: "Analytics" },
  { key: "system", label: "System" },
  { key: "critical", label: "Critical" },
];

const CATEGORY_LABEL: Record<ActivityCategory, string> = {
  trading: "Trading",
  ai: "AI",
  risk: "Risk",
  analytics: "Analytics",
  system: "System",
};

const SEVERITY_DOT: Record<ActivitySeverity, string> = {
  info: "bg-open",
  success: "bg-ok",
  warning: "bg-warn",
  critical: "bg-danger",
};

function matchesFilter(event: ActivityEvent, filter: Filter): boolean {
  if (filter === "all") return true;
  if (filter === "critical") return event.severity === "critical";
  return event.category === filter;
}

export function ActivityTimeline() {
  const [filter, setFilter] = useState<Filter>("all");
  const sseConnected = useLiveUpdatesConnected();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["activity"],
    queryFn: () => fetchActivity({ limit: 150 }),
    refetchInterval: pollInterval(sseConnected, 10_000),
  });

  const events = (data?.events ?? []).filter((e) => matchesFilter(e, filter));

  return (
    <section className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-3 text-sm font-semibold text-muted uppercase tracking-wide">Activity</h2>

      <div className="mb-4 flex flex-wrap gap-2">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            className={`rounded-full border px-3 py-1 text-xs transition-colors ${
              filter === f.key
                ? "border-open bg-open/10 text-foreground"
                : "border-border text-muted hover:text-foreground"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {isLoading && <p className="text-sm text-muted">Loading…</p>}
      {isError && <p className="text-sm text-danger">Could not load activity.</p>}
      {data && events.length === 0 && (
        <p className="py-8 text-center text-sm text-muted">Nothing to show for this filter.</p>
      )}

      {events.length > 0 && (
        <ol className="divide-y divide-border">
          {events.map((event) => (
            <li key={event.id} className="flex gap-3 py-3">
              <span className={`mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full ${SEVERITY_DOT[event.severity]}`} />
              <div className="min-w-0 flex-1">
                <div className="mb-1 flex items-center justify-between gap-2 text-xs text-muted">
                  <span className="font-medium text-foreground">{CATEGORY_LABEL[event.category]}</span>
                  <span>{formatClock(event.timestamp)}</span>
                </div>
                <p className="text-sm">{event.title}</p>
                {event.description && (
                  <p className="mt-0.5 text-xs text-muted">{event.description}</p>
                )}
                {event.correlation_id && (
                  <Link
                    href={`/trades/${encodeURIComponent(event.correlation_id)}`}
                    className="mt-1 inline-block text-xs text-open hover:underline"
                  >
                    view trade →
                  </Link>
                )}
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
