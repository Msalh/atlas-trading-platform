"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { pollInterval } from "@/lib/intervals";
import { useLiveUpdatesConnected } from "@/lib/live-updates";

export function KillSwitchBanner() {
  const sseConnected = useLiveUpdatesConnected();
  const { data } = useQuery({
    queryKey: ["risk"],
    queryFn: api.risk,
    refetchInterval: pollInterval(sseConnected, 5_000),
  });

  if (!data) return null;

  return (
    <div className="space-y-3">
      {!data.account_configured && (
        <div className="rounded-lg border border-warn/40 bg-warn/10 px-4 py-3 text-sm text-warn">
          Account risk parameters are using placeholder defaults (not yet configured for a
          real account) - set <code>ACCOUNT_STARTING_BALANCE</code>,{" "}
          <code>ACCOUNT_DAILY_LOSS_LIMIT</code>, <code>ACCOUNT_TRAILING_DRAWDOWN_LIMIT</code>,{" "}
          <code>ACCOUNT_MAX_CONTRACTS</code> before trusting the numbers below.
        </div>
      )}

      {data.kill_switch.should_trigger ? (
        <div className="rounded-lg border border-danger/50 bg-danger/10 px-4 py-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-danger">
            <span className="h-2 w-2 rounded-full bg-danger" />
            KILL SWITCH WOULD TRIGGER (display only - not enforced)
          </div>
          <ul className="mt-2 space-y-1 text-xs text-danger/90">
            {data.kill_switch.reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </div>
      ) : (
        <div className="flex items-center gap-2 rounded-lg border border-ok/30 bg-ok/10 px-4 py-3 text-sm text-ok">
          <span className="h-2 w-2 rounded-full bg-ok" />
          Account risk within limits.
        </div>
      )}
    </div>
  );
}
