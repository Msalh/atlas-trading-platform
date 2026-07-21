// UI v2, architecture §9. The one shared TanStack Query hook every consumer
// of GET /setup-engine/episodes/live must call - Active Setup Bundle,
// Timeline, and (later) Episode Inspector's live half. All three produce
// the identical query key for the same (symbol, timeframe, window), so
// react-query serves one shared request/cache entry per polling tick
// regardless of how many of these components are mounted at once, rather
// than each firing its own duplicate fetch.

"use client";

import { useQuery } from "@tanstack/react-query";
import { useLiveSelector } from "@/lib/liveSelector";
import { ApiFetchError, LiveEpisodesResponse, fetchLiveEpisodes } from "@/lib/setupEngineApi";

// A fixed, shared window - not user-configurable per consumer, precisely
// because a configurable window would fragment the shared query key this
// hook exists to guarantee.
export const LIVE_EPISODES_WINDOW = 500;

// Bars close every 5+ minutes at this app's timeframes (see
// ruleEngineApi.ts's TIMEFRAME_DURATION_MINUTES) - polling every 20s is a
// cheap safety net, not the primary "freshness" mechanism (that's
// data_as_of, read from the envelope and shown via FreshnessBadge).
const POLL_INTERVAL_MS = 20_000;

export function liveEpisodesQueryKey(symbol: string, timeframe: string, window: number) {
  return ["live-episodes", symbol, timeframe, window] as const;
}

export function useLiveEpisodes() {
  const { symbol, timeframe } = useLiveSelector();

  return useQuery<LiveEpisodesResponse, ApiFetchError>({
    queryKey: liveEpisodesQueryKey(symbol, timeframe, LIVE_EPISODES_WINDOW),
    queryFn: () => fetchLiveEpisodes(symbol, timeframe, LIVE_EPISODES_WINDOW),
    enabled: symbol.trim().length > 0,
    refetchInterval: POLL_INTERVAL_MS,
  });
}
