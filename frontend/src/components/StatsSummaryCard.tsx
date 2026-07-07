"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { formatPnl, formatPoints } from "@/lib/format";
import { pollInterval } from "@/lib/intervals";
import { useLiveUpdatesConnected } from "@/lib/live-updates";

function Stat({ label, value, valueClass }: { label: string; value: string; valueClass?: string }) {
  return (
    <div>
      <div className="text-[11px] uppercase text-muted">{label}</div>
      <div className={`font-mono text-base ${valueClass ?? ""}`}>{value}</div>
    </div>
  );
}

export function StatsSummaryCard() {
  const sseConnected = useLiveUpdatesConnected();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["stats", "today"],
    queryFn: api.statsToday,
    refetchInterval: pollInterval(sseConnected, 20_000),
  });

  return (
    <section className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-1 text-sm font-semibold text-muted uppercase tracking-wide">
        Today ({data?.date_utc ?? "…"} UTC)
      </h2>
      <p className="mb-3 text-[11px] text-muted">
        Lightweight summary from today&apos;s trades — not the full analytics engine.
      </p>

      {isLoading && <p className="text-sm text-muted">Loading…</p>}
      {isError && <p className="text-sm text-danger">Could not load today&apos;s stats.</p>}

      {data && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <Stat label="Entries" value={String(data.trades_entered_today)} />
            <Stat label="Closed" value={String(data.trades_closed_today)} />
            <Stat label="Wins" value={String(data.wins_today)} valueClass="text-long" />
            <Stat label="Losses" value={String(data.losses_today)} valueClass="text-short" />
          </div>

          <div className="border-t border-border pt-3">
            <Stat
              label="Realized P&L"
              value={formatPnl(data.realized_pnl_today)}
              valueClass={data.realized_pnl_today >= 0 ? "text-long" : "text-short"}
            />
          </div>

          {data.pmt_forward_failures_today > 0 && (
            <p className="rounded-md border border-warn/30 bg-warn/10 px-3 py-2 text-xs text-warn">
              {data.pmt_forward_failures_today} PickMyTrade forward failure
              {data.pmt_forward_failures_today > 1 ? "s" : ""} today
            </p>
          )}

          {data.open_position.correlation_id && (
            <div className="border-t border-border pt-3">
              <div className="mb-1 text-[11px] uppercase text-muted">Open position risk</div>
              <div className="flex gap-4 font-mono text-sm">
                <span className="text-short">risk {formatPoints(data.open_position.risk_points)} pts</span>
                <span className="text-long">reward {formatPoints(data.open_position.reward_points)} pts</span>
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
