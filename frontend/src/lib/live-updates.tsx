"use client";

import { useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useRef, useState } from "react";

export type ConnectionState = "connecting" | "open" | "closed";

const LiveUpdatesContext = createContext<ConnectionState>("connecting");

export function useLiveUpdatesState(): ConnectionState {
  return useContext(LiveUpdatesContext);
}

export function useLiveUpdatesConnected(): boolean {
  return useLiveUpdatesState() === "open";
}

// Production hardening: EventSource now connects same-origin to this app's own
// /api/stream route (app/api/stream/route.ts), which proxies to the backend's
// /api/v1/stream server-side, attaching a server-only ATLAS_API_KEY as a normal
// Authorization header. No key of any kind travels in this URL or reaches the
// browser.
const STREAM_URL = "/api/stream";

// Every event type from atlas/events/types.py that should cause a refetch. Kept as a
// flat "which query-key groups does this event affect" map rather than trying to
// invalidate by exact trade id - React Query's invalidateQueries does prefix
// matching, so invalidating ["trades"] covers current position, the history list,
// and any open trade-detail view in one call. Cheap at this app's data volume (see
// docs/sprint3/architecture-decisions.md).
function queryKeyGroupsFor(eventType: string): string[][] {
  // Every event type (trade.* and, as of Sprint 6, ai.*) affects the Connection
  // Status panel in some way (it tracks last-seen-at for TradingView/PickMyTrade/
  // Claude across all of them - see atlas/api/v1/status.py), and every trade.* event
  // affects at least one field the risk snapshot computes (open position appearing/
  // updating, or balance/drawdown moving on exit) - so both are always invalidated
  // alongside ["trades"]. AI events additionally affect ["ai"] (the notes/reports
  // panel) and, since an AI note can appear in a trade's timeline, ["trades"] too -
  // already covered by the base group.
  const groups: string[][] = [["trades"], ["status"], ["risk"]];
  if (eventType.startsWith("ai.")) {
    groups.push(["ai"]);
  }
  if (eventType === "trade.exit" || eventType === "trade.entry.received") {
    groups.push(["stats"]);
  }
  if (eventType === "trade.exit") {
    // Analytics (equity curve, win rate, breakdowns) are computed over CLOSED trades
    // only - see atlas/analytics.py - so only a trade actually closing changes them.
    groups.push(["analytics"]);
  }
  return groups;
}

export function LiveUpdatesProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const [state, setState] = useState<ConnectionState>("connecting");
  const sourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    const source = new EventSource(STREAM_URL);
    sourceRef.current = source;

    source.addEventListener("connected", () => setState("open"));

    source.addEventListener("trade", (event: MessageEvent<string>) => {
      setState("open");
      let payload: { type?: string } | null = null;
      try {
        payload = JSON.parse(event.data);
      } catch {
        return; // malformed event - ignore, the next poll will still catch up
      }
      if (!payload?.type) return;
      for (const queryKey of queryKeyGroupsFor(payload.type)) {
        queryClient.invalidateQueries({ queryKey });
      }
    });

    // EventSource retries connections on its own; onerror fires for every dropped
    // connection (transient or not) and onopen fires again once it reconnects. We
    // just track that as "closed" in between so components fall back to their normal
    // poll interval - see lib/intervals.ts.
    source.onerror = () => setState("closed");
    source.onopen = () => setState("open");

    return () => {
      source.close();
    };
  }, [queryClient]);

  return <LiveUpdatesContext.Provider value={state}>{children}</LiveUpdatesContext.Provider>;
}
