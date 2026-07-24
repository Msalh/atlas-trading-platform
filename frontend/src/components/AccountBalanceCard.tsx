"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchRisk } from "@/lib/riskApi";
import { formatPnl } from "@/lib/format";
import { pollInterval } from "@/lib/intervals";
import { useLiveUpdatesConnected } from "@/lib/live-updates";

export function AccountBalanceCard() {
  const sseConnected = useLiveUpdatesConnected();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["risk"],
    queryFn: fetchRisk,
    refetchInterval: pollInterval(sseConnected, 5_000),
  });

  return (
    <section className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-3 text-sm font-semibold text-muted uppercase tracking-wide">
        Account Balance
      </h2>
      {isLoading && <p className="text-sm text-muted">Loading…</p>}
      {isError && <p className="text-sm text-danger">Could not load account balance.</p>}
      {data && (
        <div className="grid grid-cols-3 gap-4 font-mono">
          <div>
            <div className="text-[11px] uppercase text-muted">Starting</div>
            <div className="text-base">{formatPnl(data.starting_balance)}</div>
          </div>
          <div>
            <div className="text-[11px] uppercase text-muted">Current</div>
            <div
              className={`text-base font-semibold ${
                data.current_balance >= data.starting_balance ? "text-long" : "text-short"
              }`}
            >
              {formatPnl(data.current_balance)}
            </div>
          </div>
          <div>
            <div className="text-[11px] uppercase text-muted">High-water mark</div>
            <div className="text-base">{formatPnl(data.high_water_mark)}</div>
          </div>
        </div>
      )}
    </section>
  );
}
