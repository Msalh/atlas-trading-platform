// Sprint 11A Group 4. Typed client for GET /analytics/summary, GET
// /analytics/equity-curve, and GET /analytics/breakdown, reached through the
// same-origin BFF proxy (src/lib/proxyClient.ts). Each shape is scoped to exactly the
// fields the Analytics page's four consumers (AnalyticsSummaryCards,
// EquityCurveChart, DrawdownChart, BreakdownChart via BreakdownSection)
// read - not atlas/analytics.py's full SummaryMetrics/EquityPoint/
// BreakdownGroup dataclasses.
//
// "analytics/summary", "analytics/equity-curve", "analytics/breakdown" are
// new proxy allowlist entries, added alongside this client.

import { ApiFetchError, proxyGet } from "@/lib/proxyClient";

export { ApiFetchError };

export interface AnalyticsSummaryResponse {
  total_trades: number;
  wins: number;
  losses: number;
  win_rate_pct: number;
  profit_factor: number | null;
  expectancy: number;
  avg_win: number | null;
  avg_loss: number | null;
  avg_r: number | null;
  r_multiple_sample_size: number;
}

export interface EquityPoint {
  closed_at: string;
  equity: number;
  drawdown: number;
}

export interface EquityCurveResponse {
  points: EquityPoint[];
  ending_equity: number;
  max_drawdown: number;
  max_drawdown_pct: number;
}

export interface BreakdownGroup {
  key: string;
  total_trades: number;
  win_rate_pct: number;
  total_realized_pnl: number;
}

export interface BreakdownResponse {
  by_session: BreakdownGroup[];
  by_setup: BreakdownGroup[];
  by_weekday: BreakdownGroup[];
}

function isNullableNumber(value: unknown): value is number | null {
  return value === null || typeof value === "number";
}

function isAnalyticsSummaryResponse(value: unknown): value is AnalyticsSummaryResponse {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.total_trades === "number" &&
    typeof v.wins === "number" &&
    typeof v.losses === "number" &&
    typeof v.win_rate_pct === "number" &&
    isNullableNumber(v.profit_factor) &&
    typeof v.expectancy === "number" &&
    isNullableNumber(v.avg_win) &&
    isNullableNumber(v.avg_loss) &&
    isNullableNumber(v.avg_r) &&
    typeof v.r_multiple_sample_size === "number"
  );
}

function isEquityPoint(value: unknown): value is EquityPoint {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return typeof v.closed_at === "string" && typeof v.equity === "number" && typeof v.drawdown === "number";
}

function isEquityCurveResponse(value: unknown): value is EquityCurveResponse {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    Array.isArray(v.points) &&
    v.points.every(isEquityPoint) &&
    typeof v.ending_equity === "number" &&
    typeof v.max_drawdown === "number" &&
    typeof v.max_drawdown_pct === "number"
  );
}

function isBreakdownGroup(value: unknown): value is BreakdownGroup {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.key === "string" &&
    typeof v.total_trades === "number" &&
    typeof v.win_rate_pct === "number" &&
    typeof v.total_realized_pnl === "number"
  );
}

function isBreakdownResponse(value: unknown): value is BreakdownResponse {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    Array.isArray(v.by_session) &&
    v.by_session.every(isBreakdownGroup) &&
    Array.isArray(v.by_setup) &&
    v.by_setup.every(isBreakdownGroup) &&
    Array.isArray(v.by_weekday) &&
    v.by_weekday.every(isBreakdownGroup)
  );
}

export function fetchAnalyticsSummary(): Promise<AnalyticsSummaryResponse> {
  return proxyGet("analytics/summary", {}, isAnalyticsSummaryResponse);
}

export function fetchEquityCurve(): Promise<EquityCurveResponse> {
  return proxyGet("analytics/equity-curve", {}, isEquityCurveResponse);
}

export function fetchBreakdown(): Promise<BreakdownResponse> {
  return proxyGet("analytics/breakdown", {}, isBreakdownResponse);
}
