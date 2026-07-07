"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { pollInterval } from "@/lib/intervals";
import { useLiveUpdatesConnected } from "@/lib/live-updates";
import { BreakdownChart } from "@/components/BreakdownChart";

export function BreakdownSection() {
  const sseConnected = useLiveUpdatesConnected();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["analytics", "breakdown"],
    queryFn: api.breakdown,
    refetchInterval: pollInterval(sseConnected, 30_000),
  });

  if (isLoading) return <p className="text-sm text-muted">Loading…</p>;
  if (isError) return <p className="text-sm text-danger">Could not load breakdowns.</p>;
  if (!data) return null;

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
      <BreakdownChart title="By Session" groups={data.by_session} />
      <BreakdownChart title="By Setup" groups={data.by_setup} />
      <BreakdownChart title="By Day of Week" groups={data.by_weekday} />
    </div>
  );
}
