import type { TimelineEvent } from "@/lib/api";
import { formatClock, formatPnl, formatPrice } from "@/lib/format";

const DOT_COLOR: Record<string, string> = {
  entry_received: "bg-open",
  pmt_forwarded: "bg-ok",
  pmt_forward_failed: "bg-danger",
  ai_analysis: "bg-muted",
  price_update: "bg-open",
  exit: "bg-long",
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
