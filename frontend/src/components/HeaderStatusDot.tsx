"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { pollInterval } from "@/lib/intervals";
import { useLiveUpdatesConnected } from "@/lib/live-updates";

export function HeaderStatusDot() {
  const sseConnected = useLiveUpdatesConnected();
  const { data, isError } = useQuery({
    queryKey: ["status"],
    queryFn: api.status,
    refetchInterval: pollInterval(sseConnected, 10_000),
  });

  const dbOk = data?.database.ok ?? false;
  const color = isError || !dbOk ? "bg-danger" : "bg-ok";
  const label = isError ? "backend unreachable" : dbOk ? "database ok" : "database error";

  return (
    <div className="flex items-center gap-3 text-xs text-muted">
      <span title={sseConnected ? "live updates connected" : "live updates unavailable - falling back to polling"}>
        {sseConnected ? "● live" : "○ polling"}
      </span>
      <div className="flex items-center gap-2" title={label}>
        <span className={`h-2 w-2 rounded-full ${color}`} />
        <span>{isError ? "offline" : dbOk ? "online" : "degraded"}</span>
      </div>
    </div>
  );
}
