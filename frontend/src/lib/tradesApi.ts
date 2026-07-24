// Sprint 11A Groups 2 and 6. Typed clients for GET /trades/current, GET
// /trades, and GET /trades/{id}, reached through the same-origin BFF proxy
// (src/lib/proxyClient.ts) instead of lib/api.ts's legacy
// NEXT_PUBLIC_API_KEY pattern. `Trade` covers every field any consumer of
// this file reads across all three endpoints (they return the same
// underlying repository row) - Dashboard's two consumers (CurrentPositionCard,
// TradeHistoryTable) only read a subset; Trade Detail (TradeDetailView) is
// what needs atr/ema_distance_atr/regime_slope_pct/session/
// pmt_relay_diagnostics.
//
// "trades/current" and "trades" (params: limit, status) are static proxy
// allowlist entries (Group 2). GET /trades/{id} is NOT a static entry - it's
// the one dynamic-ID path this proxy supports, validated by
// parseTradeDetailPath (src/lib/proxyAllowlist.ts) and wired into
// src/app/api/proxy/[...path]/route.ts's GET handler directly, not through
// ALLOWED_PROXY_ROUTES. See that function's own header comment for why this
// is a narrow, single-purpose structural parser, never a wildcard/prefix
// rule.

import { ApiFetchError, proxyGet } from "@/lib/proxyClient";

export { ApiFetchError };

export interface PmtRelayDiagnostics {
  attempted_at: string;
  url: string | null;
  method: string;
  payload: Record<string, unknown>;
  status_code: number | null;
  response_body: string | null;
  exception: string | null;
  duration_ms: number;
}

export interface Trade {
  correlation_id: string;
  received_at: string | null;
  direction: "long" | "short" | null;
  setup_tag: string | null;
  entry_price: number | null;
  sl: number | null;
  tp: number | null;
  status: "open" | "won" | "lost" | string;
  current_price: number | null;
  unrealized_pnl: number | null;
  realized_pnl: number | null;
  pmt_forwarded: boolean;
  pmt_error: string | null;
  atr: number | null;
  ema_distance_atr: number | null;
  regime_slope_pct: number | null;
  session: string | null;
  pmt_relay_diagnostics: PmtRelayDiagnostics | null;
}

export interface CurrentTradeResponse {
  open: boolean;
  trade: Trade | null;
}

export interface TradeListResponse {
  count: number;
  trades: Trade[];
}

// Sprint 6 timeline shapes - deliberately loose (an index signature, not a
// per-variant discriminated union), matching lib/api.ts's own prior
// TimelineEvent/Factor and atlas/api/v1/trades.py::build_timeline, which
// returns differently-shaped plain dicts per event type. TradeTimeline.tsx
// already reads each variant's extra fields via its own `as` casts against
// this same looseness - not narrowing it further here.
export type TimelineEventType =
  | "entry_received"
  | "pmt_forwarded"
  | "pmt_forward_failed"
  | "ai_analysis"
  | "entry_score"
  | "price_update"
  | "exit"
  | "post_trade_review";

export interface TimelineEvent {
  type: TimelineEventType;
  at: string | null;
  [key: string]: unknown;
}

// entry_score events (Sprint 7) carry a `factors: Factor[] | null` field
// under TimelineEvent's own index signature - exported here so
// TradeTimeline.tsx's own `event.factors as Factor[] | null` cast has a
// real type to cast against, without re-widening TimelineEvent itself into
// a per-variant discriminated union.
export interface Factor {
  name: string;
  entry_value: number | null;
  winners_median: number | null;
  losers_median: number | null;
  favorable: boolean | null;
}

export interface TradeDetailResponse {
  trade: Trade;
  timeline: TimelineEvent[];
}

function isNullableNumber(value: unknown): value is number | null {
  return value === null || typeof value === "number";
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function isPmtRelayDiagnostics(value: unknown): value is PmtRelayDiagnostics {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.attempted_at === "string" &&
    isNullableString(v.url) &&
    typeof v.method === "string" &&
    typeof v.payload === "object" &&
    v.payload !== null &&
    !Array.isArray(v.payload) &&
    isNullableNumber(v.status_code) &&
    isNullableString(v.response_body) &&
    isNullableString(v.exception) &&
    typeof v.duration_ms === "number"
  );
}

function isTrade(value: unknown): value is Trade {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.correlation_id === "string" &&
    isNullableString(v.received_at) &&
    (v.direction === null || v.direction === "long" || v.direction === "short") &&
    isNullableString(v.setup_tag) &&
    isNullableNumber(v.entry_price) &&
    isNullableNumber(v.sl) &&
    isNullableNumber(v.tp) &&
    typeof v.status === "string" &&
    isNullableNumber(v.current_price) &&
    isNullableNumber(v.unrealized_pnl) &&
    isNullableNumber(v.realized_pnl) &&
    typeof v.pmt_forwarded === "boolean" &&
    isNullableString(v.pmt_error) &&
    isNullableNumber(v.atr) &&
    isNullableNumber(v.ema_distance_atr) &&
    isNullableNumber(v.regime_slope_pct) &&
    isNullableString(v.session) &&
    (v.pmt_relay_diagnostics === null || isPmtRelayDiagnostics(v.pmt_relay_diagnostics))
  );
}

function isCurrentTradeResponse(value: unknown): value is CurrentTradeResponse {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return typeof v.open === "boolean" && (v.trade === null || isTrade(v.trade));
}

function isTradeListResponse(value: unknown): value is TradeListResponse {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return typeof v.count === "number" && Array.isArray(v.trades) && v.trades.every(isTrade);
}

const TIMELINE_EVENT_TYPES: readonly TimelineEventType[] = [
  "entry_received",
  "pmt_forwarded",
  "pmt_forward_failed",
  "ai_analysis",
  "entry_score",
  "price_update",
  "exit",
  "post_trade_review",
];

function isTimelineEvent(value: unknown): value is TimelineEvent {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.type === "string" &&
    (TIMELINE_EVENT_TYPES as readonly string[]).includes(v.type) &&
    isNullableString(v.at)
  );
}

function isTradeDetailResponse(value: unknown): value is TradeDetailResponse {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return isTrade(v.trade) && Array.isArray(v.timeline) && v.timeline.every(isTimelineEvent);
}

export function fetchCurrentTrade(): Promise<CurrentTradeResponse> {
  return proxyGet("trades/current", {}, isCurrentTradeResponse);
}

export function fetchTradeList(params?: { limit?: number; status?: string }): Promise<TradeListResponse> {
  const query: Record<string, string> = {};
  if (params?.limit !== undefined) query.limit = String(params.limit);
  if (params?.status !== undefined) query.status = params.status;
  return proxyGet("trades", query, isTradeListResponse);
}

// Mirrors lib/api.ts's old api.tradeDetail: resolves to null on a 404
// (no trade found for this ID) rather than throwing, so TradeDetailView's
// existing "no trade found" empty state keeps working unchanged - the only
// place in this migration that catches a specific ApiFetchError kind rather
// than letting every error propagate to the caller.
export async function fetchTradeDetail(correlationId: string): Promise<TradeDetailResponse | null> {
  try {
    return await proxyGet(`trades/${encodeURIComponent(correlationId)}`, {}, isTradeDetailResponse);
  } catch (err) {
    if (err instanceof ApiFetchError && err.kind === "not_found") return null;
    throw err;
  }
}
