"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { fetchRisk } from "@/lib/riskApi";
import { pollInterval } from "@/lib/intervals";
import { useLiveUpdatesConnected } from "@/lib/live-updates";

export function HeaderKillSwitchDot() {
  const sseConnected = useLiveUpdatesConnected();
  const { data } = useQuery({
    queryKey: ["risk"],
    queryFn: fetchRisk,
    refetchInterval: pollInterval(sseConnected, 5_000),
  });

  if (!data) return null;

  const triggered = data.kill_switch.should_trigger;
  return (
    <Link
      href="/account"
      className="flex items-center gap-1.5 text-xs"
      title={triggered ? data.kill_switch.reasons.join("; ") : "account risk within limits"}
    >
      <span className={`h-2 w-2 rounded-full ${triggered ? "bg-danger" : "bg-ok"}`} />
      <span className={triggered ? "font-semibold text-danger" : "text-muted"}>
        {triggered ? "risk limit" : "risk ok"}
      </span>
    </Link>
  );
}
