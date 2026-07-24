// Sprint 11A Group 2. Typed clients for GET /trades/current and GET /trades,
// reached through the same-origin BFF proxy (src/lib/proxyClient.ts) instead
// of lib/api.ts's legacy NEXT_PUBLIC_API_KEY pattern. `Trade` here is
// intentionally scoped to only the fields Dashboard's two consumers
// (CurrentPositionCard, TradeHistoryTable) read - not the full ~29-field row
// atlas/api/v1/trades.py returns. Trade Detail (Sprint 11A Group 6) needs a
// wider set of fields (session/llm/pmt-diagnostics/etc.) and is expected to
// extend this file with its own fetchTradeDetail + a fuller Trade shape
// then, when that group actually starts - not built speculatively here.
//
// "trades/current" and "trades" (params: limit, status) are new proxy
// allowlist entries, added alongside this client.

import { ApiFetchError, proxyGet } from "@/lib/proxyClient";

export { ApiFetchError };

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
}

export interface CurrentTradeResponse {
  open: boolean;
  trade: Trade | null;
}

export interface TradeListResponse {
  count: number;
  trades: Trade[];
}

function isNullableNumber(value: unknown): value is number | null {
  return value === null || typeof value === "number";
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
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
    isNullableString(v.pmt_error)
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

export function fetchCurrentTrade(): Promise<CurrentTradeResponse> {
  return proxyGet("trades/current", {}, isCurrentTradeResponse);
}

export function fetchTradeList(params?: { limit?: number; status?: string }): Promise<TradeListResponse> {
  const query: Record<string, string> = {};
  if (params?.limit !== undefined) query.limit = String(params.limit);
  if (params?.status !== undefined) query.status = params.status;
  return proxyGet("trades", query, isTradeListResponse);
}
