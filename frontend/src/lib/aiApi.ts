// Sprint 11A Group 7. Typed client for the AI read and report-trigger
// endpoints, reached exclusively through the same-origin BFF proxy.

import { ApiFetchError, proxyGet, proxyPost } from "@/lib/proxyClient";
import type { AnalyticsSummaryResponse } from "@/lib/analyticsApi";

export { ApiFetchError };

export type AiNoteType = "entry_score" | "post_trade_review" | "daily_report" | "weekly_report";
export type ReportPeriod = "daily" | "weekly";

export interface Factor {
  name: string;
  entry_value: number | null;
  winners_median: number | null;
  losers_median: number | null;
  favorable: boolean | null;
}

export interface AiNote {
  id: number;
  trade_correlation_id: string | null;
  note_type: AiNoteType;
  created_at: string;
  model: string | null;
  score: number | null;
  score_label: string | null;
  content: string | null;
  error: string | null;
  expected_r: number | null;
  historical_win_rate_pct: number | null;
  similar_trade_count: number | null;
  factors: Factor[] | null;
}

export interface AiNotesResponse {
  count: number;
  notes: AiNote[];
}

export interface AiReportsResponse {
  count: number;
  reports: AiNote[];
}

export interface ReportTriggerResponse {
  ok: true;
  status: "generating";
  period: ReportPeriod;
}

export interface IntelligenceSnapshot {
  correlation_id: string;
  similar_trade_count: number;
  confidence_score: number | null;
  confidence_label: string;
  summary: AnalyticsSummaryResponse;
  factors: Factor[];
}

function isNullableNumber(value: unknown): value is number | null {
  return value === null || typeof value === "number";
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function isFactor(value: unknown): value is Factor {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.name === "string" &&
    isNullableNumber(v.entry_value) &&
    isNullableNumber(v.winners_median) &&
    isNullableNumber(v.losers_median) &&
    (v.favorable === null || typeof v.favorable === "boolean")
  );
}

const NOTE_TYPES: readonly AiNoteType[] = [
  "entry_score",
  "post_trade_review",
  "daily_report",
  "weekly_report",
];

function isAiNote(value: unknown): value is AiNote {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.id === "number" &&
    isNullableString(v.trade_correlation_id) &&
    typeof v.note_type === "string" &&
    (NOTE_TYPES as readonly string[]).includes(v.note_type) &&
    typeof v.created_at === "string" &&
    isNullableString(v.model) &&
    isNullableNumber(v.score) &&
    isNullableString(v.score_label) &&
    isNullableString(v.content) &&
    isNullableString(v.error) &&
    isNullableNumber(v.expected_r) &&
    isNullableNumber(v.historical_win_rate_pct) &&
    isNullableNumber(v.similar_trade_count) &&
    (v.factors === null || (Array.isArray(v.factors) && v.factors.every(isFactor)))
  );
}

function isAiNotesResponse(value: unknown): value is AiNotesResponse {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return typeof v.count === "number" && Array.isArray(v.notes) && v.notes.every(isAiNote);
}

function isAiReportsResponse(value: unknown): value is AiReportsResponse {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return typeof v.count === "number" && Array.isArray(v.reports) && v.reports.every(isAiNote);
}

function isAnalyticsSummary(value: unknown): value is AnalyticsSummaryResponse {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.total_trades === "number" &&
    typeof v.wins === "number" &&
    typeof v.losses === "number" &&
    typeof v.win_rate_pct === "number" &&
    typeof v.gross_profit === "number" &&
    typeof v.gross_loss === "number" &&
    isNullableNumber(v.profit_factor) &&
    typeof v.expectancy === "number" &&
    isNullableNumber(v.avg_win) &&
    isNullableNumber(v.avg_loss) &&
    isNullableNumber(v.avg_r) &&
    typeof v.r_multiple_sample_size === "number"
  );
}

function isIntelligenceSnapshot(value: unknown): value is IntelligenceSnapshot {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.correlation_id === "string" &&
    typeof v.similar_trade_count === "number" &&
    isNullableNumber(v.confidence_score) &&
    typeof v.confidence_label === "string" &&
    isAnalyticsSummary(v.summary) &&
    Array.isArray(v.factors) &&
    v.factors.every(isFactor)
  );
}

function isReportTriggerResponse(value: unknown): value is ReportTriggerResponse {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    v.ok === true &&
    v.status === "generating" &&
    (v.period === "daily" || v.period === "weekly")
  );
}

export function fetchAiNotes(params?: {
  tradeCorrelationId?: string;
  noteType?: AiNoteType;
  limit?: number;
}): Promise<AiNotesResponse> {
  const query: Record<string, string> = {};
  if (params?.tradeCorrelationId !== undefined) query.trade_correlation_id = params.tradeCorrelationId;
  if (params?.noteType !== undefined) query.note_type = params.noteType;
  if (params?.limit !== undefined) query.limit = String(params.limit);
  return proxyGet("ai/notes", query, isAiNotesResponse);
}

export function fetchAiReports(params?: {
  period?: ReportPeriod;
  limit?: number;
}): Promise<AiReportsResponse> {
  const query: Record<string, string> = {};
  if (params?.period !== undefined) query.period = params.period;
  if (params?.limit !== undefined) query.limit = String(params.limit);
  return proxyGet("ai/reports", query, isAiReportsResponse);
}

export function triggerReport(period: ReportPeriod): Promise<ReportTriggerResponse> {
  return proxyPost(`ai/reports/${period}`, undefined, isReportTriggerResponse);
}

export async function fetchIntelligence(correlationId: string): Promise<IntelligenceSnapshot | null> {
  try {
    return await proxyGet(
      `ai/intelligence/${encodeURIComponent(correlationId)}`,
      {},
      isIntelligenceSnapshot,
    );
  } catch (err) {
    if (err instanceof ApiFetchError && err.kind === "not_found") return null;
    throw err;
  }
}
