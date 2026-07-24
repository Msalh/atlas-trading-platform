"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { fetchTradeList } from "@/lib/tradesApi";
import { formatClock, formatPnl, formatPrice } from "@/lib/format";
import { pollInterval } from "@/lib/intervals";
import { useLiveUpdatesConnected } from "@/lib/live-updates";
import { DirectionBadge, StatusBadge } from "@/components/StatusBadge";

const FILTERS = [
  { label: "All", value: undefined },
  { label: "Open", value: "open" },
  { label: "Won", value: "won" },
  { label: "Lost", value: "lost" },
] as const;

export function TradeHistoryTable() {
  const [status, setStatus] = useState<string | undefined>(undefined);
  const sseConnected = useLiveUpdatesConnected();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["trades", "list", status],
    queryFn: () => fetchTradeList({ limit: 50, status }),
    refetchInterval: pollInterval(sseConnected, 15_000),
  });

  return (
    <section className="rounded-lg border border-border bg-surface p-5">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-muted uppercase tracking-wide">Trade History</h2>
        <div className="flex gap-1">
          {FILTERS.map((f) => (
            <button
              key={f.label}
              onClick={() => setStatus(f.value)}
              className={`rounded px-2 py-1 text-xs ${
                status === f.value
                  ? "bg-open/20 text-open"
                  : "text-muted hover:bg-surface-raised"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {isLoading && <p className="text-sm text-muted">Loading…</p>}
      {isError && <p className="text-sm text-danger">Could not load trade history.</p>}

      {data && data.trades.length === 0 && (
        <p className="py-8 text-center text-sm text-muted">No trades yet.</p>
      )}

      {data && data.trades.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-border text-[11px] uppercase text-muted">
                <th className="py-2 pr-3 font-medium">Received</th>
                <th className="py-2 pr-3 font-medium">Dir</th>
                <th className="py-2 pr-3 font-medium">Setup</th>
                <th className="py-2 pr-3 font-medium">Entry</th>
                <th className="py-2 pr-3 font-medium">Status</th>
                <th className="py-2 pr-3 font-medium">P&amp;L</th>
                <th className="py-2 pr-3 font-medium">Relay</th>
                <th className="py-2 pr-3 font-medium"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border font-mono">
              {data.trades.map((t) => (
                <tr key={t.correlation_id} className="hover:bg-surface-raised">
                  <td className="py-2 pr-3 whitespace-nowrap">{formatClock(t.received_at)}</td>
                  <td className="py-2 pr-3">
                    <DirectionBadge direction={t.direction} />
                  </td>
                  <td className="py-2 pr-3 font-sans text-muted">{t.setup_tag ?? "-"}</td>
                  <td className="py-2 pr-3">{formatPrice(t.entry_price)}</td>
                  <td className="py-2 pr-3">
                    <StatusBadge status={t.status} />
                  </td>
                  <td
                    className={`py-2 pr-3 ${
                      t.status === "open"
                        ? "text-muted"
                        : (t.realized_pnl ?? 0) >= 0
                          ? "text-long"
                          : "text-short"
                    }`}
                  >
                    {t.status === "open" ? formatPnl(t.unrealized_pnl) : formatPnl(t.realized_pnl)}
                  </td>
                  <td className="py-2 pr-3">
                    {t.pmt_forwarded ? (
                      <span className="text-ok">ok</span>
                    ) : (
                      <span className="text-danger" title={t.pmt_error ?? undefined}>
                        failed
                      </span>
                    )}
                  </td>
                  <td className="py-2 pr-3 font-sans">
                    <Link
                      href={`/trades/${encodeURIComponent(t.correlation_id)}`}
                      className="text-open hover:underline"
                    >
                      details
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
