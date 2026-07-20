// UI v2, architecture §8, F5 ("Layout-level shared LIVE symbol/timeframe
// selector"). "LIVE sections share ONE selector, defined once at a layout
// level" - Market View, Active Setup Bundle, Timeline, and Episode
// Inspector (its live current-episode half) all read/write the same
// (symbol, timeframe) pair through this context, wired once in the root
// layout, rather than each page owning its own local state. FROZEN pages
// (Research Overview, Dataset Health) do not write here - they still
// render their own manifest-locked identity, only reading a live selector
// value for the §8 mismatch comparison where relevant.

"use client";

import { createContext, useContext, useMemo, useState } from "react";

export interface LiveSelectorValue {
  symbol: string;
  timeframe: string;
  setSymbol: (symbol: string) => void;
  setTimeframe: (timeframe: string) => void;
}

const DEFAULT_SYMBOL = "MNQU6";
const DEFAULT_TIMEFRAME = "5m";

const LiveSelectorContext = createContext<LiveSelectorValue | null>(null);

export function LiveSelectorProvider({ children }: { children: React.ReactNode }) {
  const [symbol, setSymbol] = useState(DEFAULT_SYMBOL);
  const [timeframe, setTimeframe] = useState(DEFAULT_TIMEFRAME);

  const value = useMemo(() => ({ symbol, timeframe, setSymbol, setTimeframe }), [symbol, timeframe]);

  return <LiveSelectorContext.Provider value={value}>{children}</LiveSelectorContext.Provider>;
}

export function useLiveSelector(): LiveSelectorValue {
  const ctx = useContext(LiveSelectorContext);
  if (!ctx) throw new Error("useLiveSelector must be used within a LiveSelectorProvider");
  return ctx;
}
