"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { api } from "@/lib/api";
import { formatPnl, formatPrice, formatTimeAgo } from "@/lib/format";
import { pollInterval } from "@/lib/intervals";
import { useLiveUpdatesConnected } from "@/lib/live-updates";
import { DirectionBadge, StatusBadge } from "@/components/StatusBadge";
import { EntryScoreBadge } from "@/components/EntryScoreBadge";

export function CurrentPositionCard() {
  const sseConnected = useLiveUpdatesConnected();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["trades", "current"],
    queryFn: api.currentTrade,
    refetchInterval: pollInterval(sseConnected, 5_000),
  });

  return (
    <section className="rounded-lg border border-border bg-surface p-5">
      <h2 className="mb-3 text-sm font-semibold text-muted uppercase tracking-wide">
        Current Position
      </h2>

      {isLoading && <p className="text-sm text-muted">Loading…</p>}
      {isError && <p className="text-sm text-danger">Could not load the current position.</p>}

      {data && !data.open && (
        <div className="flex items-center justify-center rounded-md border border-dashed border-border py-10 text-sm text-muted">
          Flat — no open position.
        </div>
      )}

      {data?.open && data.trade && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <DirectionBadge direction={data.trade.direction} />
              <span className="text-muted">{data.trade.setup_tag ?? "?"}</span>
              <StatusBadge status={data.trade.status} />
              <EntryScoreBadge correlationId={data.trade.correlation_id} />
            </div>
            <span className="text-xs text-muted">
              opened {formatTimeAgo(data.trade.received_at)}
            </span>
          </div>

          <div className="grid grid-cols-3 gap-4 rounded-md bg-surface-raised p-4 font-mono text-sm">
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
          </div>

          <div className="flex items-center justify-between rounded-md bg-surface-raised p-4">
            <div>
              <div className="text-[11px] uppercase text-muted">Current price</div>
              <div className="font-mono text-lg">{formatPrice(data.trade.current_price)}</div>
            </div>
            <div className="text-right">
              <div className="text-[11px] uppercase text-muted">Unrealized P&amp;L</div>
              <div
                className={`font-mono text-lg font-semibold ${
                  (data.trade.unrealized_pnl ?? 0) >= 0 ? "text-long" : "text-short"
                }`}
              >
                {formatPnl(data.trade.unrealized_pnl)}
              </div>
            </div>
          </div>

          {!data.trade.pmt_forwarded && (
            <p className="rounded-md border border-warn/30 bg-warn/10 px-3 py-2 text-xs text-warn">
              Not forwarded to PickMyTrade{data.trade.pmt_error ? `: ${data.trade.pmt_error}` : ""}
            </p>
          )}

          <Link
            href={`/trades/${encodeURIComponent(data.trade.correlation_id)}`}
            className="inline-block text-xs text-open hover:underline"
          >
            View timeline →
          </Link>
        </div>
      )}
    </section>
  );
}
