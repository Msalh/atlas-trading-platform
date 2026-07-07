"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { formatPnl } from "@/lib/format";
import { pollInterval } from "@/lib/intervals";
import { useLiveUpdatesConnected } from "@/lib/live-updates";
import { RiskProgressBar } from "@/components/RiskProgressBar";

export function DailyLossCard() {
  const sseConnected = useLiveUpdatesConnected();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["risk"],
    queryFn: api.risk,
    refetchInterval: pollInterval(sseConnected, 5_000),
  });

  return (
    <section className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-3 text-sm font-semibold text-muted uppercase tracking-wide">
        Daily Loss
      </h2>
      {isLoading && <p className="text-sm text-muted">Loading…</p>}
      {isError && <p className="text-sm text-danger">Could not load daily loss data.</p>}
      {data && (
        <div className="space-y-3">
          <div className="flex items-baseline justify-between font-mono text-sm">
            <span className={data.daily_loss_limit_breached ? "text-danger font-semibold" : ""}>
              {formatPnl(-data.daily_loss_used)} used
            </span>
            <span className="text-muted">of {formatPnl(data.daily_loss_limit)} limit</span>
          </div>
          <RiskProgressBar
            usedPct={(data.daily_loss_used / data.daily_loss_limit) * 100}
            breached={data.daily_loss_limit_breached}
          />
          <div className="flex justify-between text-xs text-muted">
            <span>Realized today: {formatPnl(data.daily_realized_pnl)}</span>
            <span>Remaining: {formatPnl(data.daily_loss_remaining)}</span>
          </div>
          {data.daily_loss_limit_breached && (
            <p className="text-xs font-semibold text-danger">Daily loss limit reached.</p>
          )}
        </div>
      )}
    </section>
  );
}
