"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { api } from "@/lib/api";
import { formatPnl, formatPrice } from "@/lib/format";
import { pollInterval } from "@/lib/intervals";
import { useLiveUpdatesConnected } from "@/lib/live-updates";
import { DirectionBadge, StatusBadge } from "@/components/StatusBadge";
import { TradeTimeline } from "@/components/TradeTimeline";

export function TradeDetailView({ correlationId }: { correlationId: string }) {
  const sseConnected = useLiveUpdatesConnected();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["trades", "detail", correlationId],
    queryFn: () => api.tradeDetail(correlationId),
    refetchInterval: pollInterval(sseConnected, 5_000),
  });

  return (
    <div className="space-y-6">
      <Link href="/" className="text-xs text-open hover:underline">
        ← Back to dashboard
      </Link>

      {isLoading && <p className="text-sm text-muted">Loading…</p>}
      {isError && <p className="text-sm text-danger">Could not load this trade.</p>}
      {data === null && (
        <p className="rounded-lg border border-border bg-surface p-5 text-sm text-muted">
          No trade found for correlation_id <span className="font-mono">{correlationId}</span>.
        </p>
      )}

      {data && (
        <>
          <section className="rounded-lg border border-border bg-surface p-5">
            <div className="mb-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <DirectionBadge direction={data.trade.direction} />
                <span className="text-muted">{data.trade.setup_tag ?? "?"}</span>
                <StatusBadge status={data.trade.status} />
              </div>
              <span className="font-mono text-xs text-muted">{data.trade.correlation_id}</span>
            </div>

            <div className="grid grid-cols-2 gap-4 font-mono text-sm sm:grid-cols-4">
              <div>
                <div className="text-[11px] uppercase text-muted">Entry</div>
                <div>{formatPrice(data.trade.entry_price)}</div>
              </div>
              <div>
                <div className="text-[11px] uppercase text-muted">Stop</div>
                <div className="text-short">{formatPrice(data.trade.sl)}</div>
              </div>
              <div>
                <div className="text-[11px] uppercase text-muted">Target</div>
                <div className="text-long">{formatPrice(data.trade.tp)}</div>
              </div>
              <div>
                <div className="text-[11px] uppercase text-muted">
                  {data.trade.status === "open" ? "Unrealized P&L" : "Realized P&L"}
                </div>
                <div
                  className={
                    (data.trade.status === "open" ? data.trade.unrealized_pnl : data.trade.realized_pnl) ?? 0
                      ? ((data.trade.status === "open" ? data.trade.unrealized_pnl : data.trade.realized_pnl) ?? 0) >= 0
                        ? "text-long"
                        : "text-short"
                      : ""
                  }
                >
                  {formatPnl(data.trade.status === "open" ? data.trade.unrealized_pnl : data.trade.realized_pnl)}
                </div>
              </div>
            </div>

            <div className="mt-4 grid grid-cols-2 gap-4 text-xs text-muted sm:grid-cols-4">
              <div>ATR: {data.trade.atr ?? "-"}</div>
              <div>EMA dist (ATR): {data.trade.ema_distance_atr ?? "-"}</div>
              <div>Regime slope: {data.trade.regime_slope_pct ?? "-"}%</div>
              <div>Session: {data.trade.session ?? "-"}</div>
            </div>
          </section>

          <section className="rounded-lg border border-border bg-surface p-5">
            <h2 className="mb-4 text-sm font-semibold text-muted uppercase tracking-wide">
              Timeline
            </h2>
            <TradeTimeline events={data.timeline} />
          </section>
        </>
      )}
    </div>
  );
}
