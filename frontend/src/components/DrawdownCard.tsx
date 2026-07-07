"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { formatPnl } from "@/lib/format";
import { pollInterval } from "@/lib/intervals";
import { useLiveUpdatesConnected } from "@/lib/live-updates";
import { RiskProgressBar } from "@/components/RiskProgressBar";

export function DrawdownCard() {
  const sseConnected = useLiveUpdatesConnected();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["risk"],
    queryFn: api.risk,
    refetchInterval: pollInterval(sseConnected, 5_000),
  });

  const usedPct =
    data && data.trailing_drawdown_limit > 0
      ? ((data.high_water_mark - data.current_balance) / data.trailing_drawdown_limit) * 100
      : 0;

  return (
    <section className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-3 text-sm font-semibold text-muted uppercase tracking-wide">
        Trailing Drawdown
      </h2>
      {isLoading && <p className="text-sm text-muted">Loading…</p>}
      {isError && <p className="text-sm text-danger">Could not load drawdown data.</p>}
      {data && (
        <div className="space-y-3">
          <div className="flex items-baseline justify-between font-mono text-sm">
            <span className={data.trailing_drawdown_breached ? "text-danger font-semibold" : ""}>
              {formatPnl(data.high_water_mark - data.current_balance)} pulled back
            </span>
            <span className="text-muted">of {formatPnl(data.trailing_drawdown_limit)} limit</span>
          </div>
          <RiskProgressBar usedPct={usedPct} breached={data.trailing_drawdown_breached} />
          <div className="flex justify-between text-xs text-muted">
            <span>Trailing stop: {formatPnl(data.trailing_stop_balance)}</span>
            <span>Remaining: {formatPnl(data.remaining_drawdown)}</span>
          </div>
          {data.trailing_drawdown_breached && (
            <p className="text-xs font-semibold text-danger">Trailing drawdown breached.</p>
          )}
        </div>
      )}
    </section>
  );
}
