import type { Factor, TimelineEvent } from "@/lib/api";
import { formatClock, formatPnl, formatPrice } from "@/lib/format";

function FactorChips({ factors }: { factors: Factor[] }) {
  return (
    <div className="mt-1 flex flex-wrap gap-1.5">
      {factors.map((f) => {
        const colorClass =
          f.favorable === true
            ? "text-long border-long/30 bg-long/10"
            : f.favorable === false
              ? "text-short border-short/30 bg-short/10"
              : "text-muted border-border bg-surface-raised";
        return (
          <span
            key={f.name}
            className={`rounded border px-1.5 py-0.5 text-[10px] font-mono ${colorClass}`}
            title={`this entry: ${f.entry_value ?? "-"}, winners median: ${f.winners_median ?? "-"}, losers median: ${f.losers_median ?? "-"}`}
          >
            {f.name}
          </span>
        );
      })}
    </div>
  );
}

const DOT_COLOR: Record<string, string> = {
  entry_received: "bg-open",
  pmt_forwarded: "bg-ok",
  pmt_forward_failed: "bg-danger",
  ai_analysis: "bg-muted",
  entry_score: "bg-muted",
  price_update: "bg-open",
  exit: "bg-long",
  post_trade_review: "bg-muted",
};

function EventLabel({ event }: { event: TimelineEvent }) {
  switch (event.type) {
    case "entry_received":
      return (
        <>
          <span className="font-semibold">Entry received</span> — {String(event.direction).toUpperCase()}{" "}
          {String(event.setup_tag ?? "")} @ {formatPrice(event.entry_price as number)}, SL{" "}
          {formatPrice(event.sl as number)} / TP {formatPrice(event.tp as number)}
        </>
      );
    case "pmt_forwarded":
      return (
        <>
          <span className="font-semibold text-ok">Forwarded to PickMyTrade</span> (HTTP{" "}
          {String(event.status_code ?? "-")})
        </>
      );
    case "pmt_forward_failed":
      return (
        <>
          <span className="font-semibold text-danger">PickMyTrade forward failed</span> —{" "}
          {String(event.error ?? "unknown error")}
        </>
      );
    case "ai_analysis":
      return event.error ? (
        <>
          <span className="font-semibold text-danger">Claude analysis failed</span> — {String(event.error)}
        </>
      ) : (
        <>
          <span className="font-semibold">Claude analysis:</span> {String(event.analysis ?? "")}
        </>
      );
    case "entry_score": {
      // Sprint 7: score/similar_trade_count/etc come from atlas/intelligence.py's
      // deterministic computation, not Claude - so a Claude failure (event.error) can
      // still coexist with a real score. Only the narrative explanation is missing.
      const factors = (event.factors as Factor[] | null) ?? null;
      const similarCount = event.similar_trade_count as number | null | undefined;
      const winRate = event.historical_win_rate_pct as number | null | undefined;
      const expectedR = event.expected_r as number | null | undefined;
      return (
        <>
          <span className="font-semibold">
            AI entry score{event.score !== null && event.score !== undefined ? `: ${event.score}/10` : ""}
            {event.score_label ? ` (${String(event.score_label)})` : ""}
          </span>
          {similarCount !== null && similarCount !== undefined && similarCount > 0 && (
            <span className="ml-1 text-xs text-muted">
              · {similarCount} similar trade{similarCount === 1 ? "" : "s"}
              {winRate !== null && winRate !== undefined ? `, ${winRate.toFixed(0)}% win rate` : ""}
              {expectedR !== null && expectedR !== undefined ? `, ${expectedR.toFixed(2)}R expected` : ""}
            </span>
          )}
          {event.error ? (
            <div className="mt-1 text-xs text-danger">Narrative unavailable — {String(event.error)}</div>
          ) : event.content ? (
            <> — {String(event.content)}</>
          ) : null}
          {factors && factors.length > 0 && <FactorChips factors={factors} />}
        </>
      );
    }
    case "post_trade_review":
      return event.error ? (
        <>
          <span className="font-semibold text-danger">Post-trade review failed</span> — {String(event.error)}
        </>
      ) : (
        <>
          <span className="font-semibold">Post-trade review:</span> {String(event.content ?? "")}
        </>
      );
    case "price_update":
      return (
        <>
          <span className="font-semibold">Price update</span> — {formatPrice(event.current_price as number)}{" "}
          (unrealized {formatPnl(event.unrealized_pnl as number)})
        </>
      );
    case "exit":
      return (
        <>
          <span className="font-semibold">Position closed</span> — {String(event.status).toUpperCase()} @{" "}
          {formatPrice(event.exit_price as number)}, realized {formatPnl(event.realized_pnl as number)}
        </>
      );
    default:
      return <span>{event.type}</span>;
  }
}

export function TradeTimeline({ events }: { events: TimelineEvent[] }) {
  if (events.length === 0) {
    return <p className="text-sm text-muted">No events recorded for this trade.</p>;
  }

  return (
    <ol className="space-y-4">
      {events.map((event, i) => (
        <li key={`${event.type}-${i}`} className="flex gap-3">
          <div className="flex flex-col items-center">
            <span className={`mt-1 h-2.5 w-2.5 shrink-0 rounded-full ${DOT_COLOR[event.type] ?? "bg-muted"}`} />
            {i < events.length - 1 && <span className="w-px flex-1 bg-border" />}
          </div>
          <div className="pb-4">
            <div className="text-xs text-muted">{event.at ? formatClock(event.at) : "time not tracked"}</div>
            <div className="text-sm">
              <EventLabel event={event} />
            </div>
          </div>
        </li>
      ))}
    </ol>
  );
}
