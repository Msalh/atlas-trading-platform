"use client";

import { useQuery } from "@tanstack/react-query";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "@/lib/api";
import { formatDateShort, formatPnl } from "@/lib/format";
import { pollInterval } from "@/lib/intervals";
import { useLiveUpdatesConnected } from "@/lib/live-updates";

export function EquityCurveChart() {
  const sseConnected = useLiveUpdatesConnected();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["analytics", "equity-curve"],
    queryFn: api.equityCurve,
    refetchInterval: pollInterval(sseConnected, 30_000),
  });

  return (
    <section className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-muted uppercase tracking-wide">Equity Curve</h2>
        {data && data.points.length > 0 && (
          <span className="font-mono text-xs text-muted">
            Ending {formatPnl(data.ending_equity)} &middot; Max DD {formatPnl(-data.max_drawdown)}
          </span>
        )}
      </div>
      {isLoading && <p className="text-sm text-muted">Loading…</p>}
      {isError && <p className="text-sm text-danger">Could not load the equity curve.</p>}
      {data && data.points.length === 0 && (
        <p className="py-8 text-center text-sm text-muted">No closed trades yet.</p>
      )}
      {data && data.points.length > 0 && (
        <div className="h-64 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data.points} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="equityFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--color-open)" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="var(--color-open)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
              <XAxis
                dataKey="closed_at"
                tickFormatter={(v: string) => formatDateShort(v)}
                stroke="var(--color-muted)"
                fontSize={11}
              />
              <YAxis
                stroke="var(--color-muted)"
                fontSize={11}
                domain={["auto", "auto"]}
                tickFormatter={(v: number) => v.toLocaleString()}
                width={70}
              />
              <Tooltip
                contentStyle={{
                  background: "var(--color-surface-raised)",
                  border: "1px solid var(--color-border)",
                  fontSize: 12,
                }}
                labelFormatter={(label) => formatDateShort(label as string)}
                formatter={(value) => [formatPnl(Number(value)), "Equity"]}
              />
              <Area type="monotone" dataKey="equity" stroke="var(--color-open)" fill="url(#equityFill)" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  );
}
