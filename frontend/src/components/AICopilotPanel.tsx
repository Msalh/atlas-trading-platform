"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { api, Factor } from "@/lib/api";
import { formatPct, formatPnl, formatRatio } from "@/lib/format";
import { pollInterval } from "@/lib/intervals";
import { useLiveUpdatesConnected } from "@/lib/live-updates";
import { DirectionBadge, StatusBadge } from "@/components/StatusBadge";
import { buildManagementNotes } from "@/lib/copilotNotes";

// Sprint - AI Copilot Phase 1: same rubric/colors as EntryScoreBadge.tsx and
// TradeTimeline.tsx's FactorChips - reused here rather than duplicated with different
// values, so a "High Confidence" badge always means the same thing everywhere.
const LABEL_COLOR: Record<string, string> = {
  "High Confidence": "text-long border-long/30 bg-long/10",
  "Moderate Confidence": "text-open border-open/30 bg-open/10",
  "Low Confidence": "text-warn border-warn/30 bg-warn/10",
  "Insufficient History": "text-muted border-border bg-surface-raised",
};

function FactorChip({ factor }: { factor: Factor }) {
  const colorClass =
    factor.favorable === true
      ? "text-long border-long/30 bg-long/10"
      : factor.favorable === false
        ? "text-short border-short/30 bg-short/10"
        : "text-muted border-border bg-surface-raised";
  return (
    <span
      className={`rounded border px-1.5 py-0.5 text-[10px] font-mono ${colorClass}`}
      title={`this entry: ${factor.entry_value ?? "-"}, winners median: ${factor.winners_median ?? "-"}, losers median: ${factor.losers_median ?? "-"}`}
    >
      {factor.name}
    </span>
  );
}

export function AICopilotPanel() {
  const sseConnected = useLiveUpdatesConnected();

  const { data: currentTrade, isLoading: tradeLoading, isError: tradeError } = useQuery({
    queryKey: ["trades", "current"],
    queryFn: api.currentTrade,
    refetchInterval: pollInterval(sseConnected, 5_000),
  });

  const correlationId = currentTrade?.open ? currentTrade.trade?.correlation_id : undefined;

  const { data: intelligence, isLoading: intelligenceLoading } = useQuery({
    queryKey: ["ai", "intelligence", correlationId],
    queryFn: () => api.intelligence(correlationId!),
    enabled: !!correlationId,
  });

  const { data: risk } = useQuery({
    queryKey: ["risk"],
    queryFn: api.risk,
    refetchInterval: pollInterval(sseConnected, 5_000),
    enabled: !!correlationId,
  });

  const { data: analyticsSummary } = useQuery({
    queryKey: ["analytics", "summary"],
    queryFn: api.analyticsSummary,
    enabled: !!correlationId,
  });

  return (
    <section className="rounded-lg border border-border bg-surface p-5">
      <h2 className="mb-3 text-sm font-semibold text-muted uppercase tracking-wide">AI Copilot</h2>

      {tradeLoading && <p className="text-sm text-muted">Loading…</p>}
      {tradeError && <p className="text-sm text-danger">Could not load the current position.</p>}

      {currentTrade && !currentTrade.open && (
        <div className="flex items-center justify-center rounded-md border border-dashed border-border py-10 text-sm text-muted">
          No open position — Copilot activates once a trade is open.
        </div>
      )}

      {currentTrade?.open && currentTrade.trade && correlationId && (
        <div className="space-y-5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <DirectionBadge direction={currentTrade.trade.direction} />
              <span className="text-muted">{currentTrade.trade.setup_tag ?? "?"}</span>
              <StatusBadge status={currentTrade.trade.status} />
            </div>
            <Link
              href={`/trades/${encodeURIComponent(correlationId)}`}
              className="text-xs text-open hover:underline"
            >
              view trade →
            </Link>
          </div>

          {intelligenceLoading && <p className="text-sm text-muted">Computing intelligence…</p>}

          {intelligence && (
            <>
              <div className="flex items-center gap-3">
                {intelligence.confidence_score !== null ? (
                  <span
                    className={`inline-flex items-center gap-1 rounded-full border px-3 py-1 text-sm font-semibold ${
                      LABEL_COLOR[intelligence.confidence_label] ?? "text-muted border-border bg-surface-raised"
                    }`}
                  >
                    {intelligence.confidence_score}/10 · {intelligence.confidence_label}
                  </span>
                ) : (
                  <span className="inline-flex items-center rounded-full border border-border bg-surface-raised px-3 py-1 text-sm font-semibold text-muted">
                    {intelligence.confidence_label}
                  </span>
                )}
              </div>

              <div className="grid grid-cols-3 gap-4 rounded-md bg-surface-raised p-4 font-mono text-sm">
                <div>
                  <div className="text-[11px] uppercase text-muted">Historical win rate</div>
                  <div>{formatPct(intelligence.summary.win_rate_pct)}</div>
                </div>
                <div>
                  <div className="text-[11px] uppercase text-muted">Expected R</div>
                  <div>{formatRatio(intelligence.summary.avg_r)}</div>
                </div>
                <div>
                  <div className="text-[11px] uppercase text-muted">Similar trades</div>
                  <div>{intelligence.similar_trade_count}</div>
                </div>
              </div>

              {intelligence.factors.length > 0 && (
                <div>
                  <div className="mb-1.5 text-[11px] uppercase text-muted">
                    Factors vs. historical winners/losers
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {intelligence.factors.map((f) => (
                      <FactorChip key={f.name} factor={f} />
                    ))}
                  </div>
                </div>
              )}
            </>
          )}

          {risk && (
            <div>
              <div className="mb-1.5 text-[11px] uppercase text-muted">Risk context</div>
              <div className="grid grid-cols-2 gap-4 rounded-md bg-surface-raised p-4 font-mono text-xs sm:grid-cols-4">
                <div>
                  <div className="text-muted">Daily loss remaining</div>
                  <div className={risk.daily_loss_limit_breached ? "text-danger" : ""}>
                    {formatPnl(risk.daily_loss_remaining)}
                  </div>
                </div>
                <div>
                  <div className="text-muted">Drawdown remaining</div>
                  <div className={risk.trailing_drawdown_breached ? "text-danger" : ""}>
                    {formatPnl(risk.remaining_drawdown)}
                  </div>
                </div>
                <div>
                  <div className="text-muted">Position risk</div>
                  <div>{formatPnl(risk.open_position?.risk_dollars ?? null)}</div>
                </div>
                <div>
                  <div className="text-muted">Position reward</div>
                  <div>{formatPnl(risk.open_position?.reward_dollars ?? null)}</div>
                </div>
              </div>
            </div>
          )}

          {analyticsSummary && (
            <p className="text-xs text-muted">
              Overall account: {formatPct(analyticsSummary.win_rate_pct)} win rate over{" "}
              {analyticsSummary.total_trades} closed trade{analyticsSummary.total_trades === 1 ? "" : "s"},
              profit factor {formatRatio(analyticsSummary.profit_factor)}.
            </p>
          )}

          {(intelligence || risk) && (
            <div>
              <div className="mb-1.5 text-[11px] uppercase text-muted">Suggested management notes</div>
              <ul className="space-y-1.5">
                {buildManagementNotes({ intelligence: intelligence ?? null, risk: risk ?? null }).map(
                  (note, i) => (
                    <li
                      key={i}
                      className={`rounded-md border px-3 py-2 text-xs ${
                        note.severity === "warning"
                          ? "border-warn/30 bg-warn/10 text-warn"
                          : "border-border bg-surface-raised text-muted"
                      }`}
                    >
                      {note.text}
                    </li>
                  ),
                )}
              </ul>
            </div>
          )}
        </div>
      )}

      <p className="mt-5 text-xs text-muted">Advisory only — never sends, modifies, cancels, or blocks orders.</p>
    </section>
  );
}
