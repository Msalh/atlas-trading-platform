"use client";

import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { BreakdownGroup } from "@/lib/analyticsApi";
import { formatPct, formatPnl } from "@/lib/format";

export function BreakdownChart({ title, groups }: { title: string; groups: BreakdownGroup[] }) {
  return (
    <section className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-3 text-sm font-semibold text-muted uppercase tracking-wide">{title}</h2>
      {groups.length === 0 ? (
        <p className="py-8 text-center text-sm text-muted">No closed trades yet.</p>
      ) : (
        <>
          <div className="h-48 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={groups} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                <XAxis dataKey="key" stroke="var(--color-muted)" fontSize={11} />
                <YAxis stroke="var(--color-muted)" fontSize={11} width={60} />
                <Tooltip
                  contentStyle={{
                    background: "var(--color-surface-raised)",
                    border: "1px solid var(--color-border)",
                    fontSize: 12,
                  }}
                  formatter={(value) => [formatPnl(Number(value)), "P&L"]}
                />
                <Bar dataKey="total_realized_pnl" radius={[3, 3, 0, 0]}>
                  {groups.map((g) => (
                    <Cell key={g.key} fill={g.total_realized_pnl >= 0 ? "var(--color-long)" : "var(--color-short)"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-3 divide-y divide-border text-xs">
            {groups.map((g) => (
              <div key={g.key} className="flex items-center justify-between py-1.5">
                <span className="font-medium">{g.key}</span>
                <span className="text-muted">
                  {g.total_trades} trades &middot; {formatPct(g.win_rate_pct)} win
                </span>
                <span className={g.total_realized_pnl >= 0 ? "text-long" : "text-short"}>
                  {formatPnl(g.total_realized_pnl)}
                </span>
              </div>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
