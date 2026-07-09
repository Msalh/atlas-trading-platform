// Typed client for the Atlas backend's versioned REST API (atlas/api/v1/*.py).
// These shapes are hand-mirrored from the FastAPI handlers, which return plain dicts
// rather than Pydantic models - keep this file in sync if a backend response shape
// changes.

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

// Sprint 9: every non-webhook, non-health backend endpoint requires this - see
// atlas/api/security.py. Left unset for local dev against scripts/dev_seed_server.py
// (which never checks it); required once NEXT_PUBLIC_API_BASE_URL points at a real
// atlas.main:app deployment, which refuses to start without a real API_KEY anyway.
const API_KEY = process.env.NEXT_PUBLIC_API_KEY;

function authHeaders(): HeadersInit {
  return API_KEY ? { Authorization: `Bearer ${API_KEY}` } : {};
}

export interface Trade {
  id: number;
  correlation_id: string;
  received_at: string;
  signal_time: string | null;
  direction: "long" | "short" | null;
  setup_tag: string | null;
  symbol: string | null;
  entry_price: number | null;
  sl: number | null;
  tp: number | null;
  atr: number | null;
  ema_distance_atr: number | null;
  regime_slope_pct: number | null;
  sweep_age_bars: number | null;
  session: string | null;
  status: "open" | "won" | "lost" | string;
  current_price: number | null;
  unrealized_pnl: number | null;
  last_update_at: string | null;
  exit_price: number | null;
  realized_pnl: number | null;
  closed_at: string | null;
  llm_model: string | null;
  llm_analysis: string | null;
  llm_error: string | null;
  pmt_forwarded: boolean;
  pmt_status_code: number | null;
  pmt_error: string | null;
  raw_entry_payload: string | null;
  pmt_relay_diagnostics: PmtRelayDiagnostics | null;
}

// Full diagnostics of the latest PickMyTrade relay attempt (added to debug why
// PickMyTrade's Alert Log was showing nothing for a relay Atlas believed succeeded -
// see atlas/services/pickmytrade.py). `payload` is the exact, normalized JSON body
// sent to PickMyTrade (data lowercased, price stringified, date ISO-8601) with the
// token masked - never the real secret.
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

export type TimelineEventType =
  | "entry_received"
  | "pmt_forwarded"
  | "pmt_forward_failed"
  | "ai_analysis" // legacy (pre-Sprint-6) single-slot analysis - see atlas/api/v1/trades.py
  | "entry_score"
  | "price_update"
  | "exit"
  | "post_trade_review";

export interface TimelineEvent {
  type: TimelineEventType;
  at: string | null;
  // entry_score events (Sprint 7) additionally carry expected_r, historical_win_rate_pct,
  // similar_trade_count, and factors: Factor[] - see atlas/api/v1/trades.py::build_timeline.
  [key: string]: unknown;
}

export interface CurrentTradeResponse {
  open: boolean;
  trade: Trade | null;
}

export interface TradeListResponse {
  count: number;
  trades: Trade[];
}

export interface TradeDetailResponse {
  trade: Trade;
  timeline: TimelineEvent[];
}

export interface StatusResponse {
  database: { ok: boolean; detail: string };
  tradingview: { last_webhook_at: string | null; last_webhook_type: string | null };
  pickmytrade: {
    configured: boolean;
    last_forward_at: string | null;
    last_forward_ok: boolean | null;
    last_error: string | null;
  };
  claude: {
    configured: boolean;
    last_analysis_at: string | null;
    last_error: string | null;
  };
}

export interface StatsTodayResponse {
  date_utc: string;
  trades_entered_today: number;
  trades_closed_today: number;
  wins_today: number;
  losses_today: number;
  realized_pnl_today: number;
  pmt_forward_failures_today: number;
  open_position: {
    correlation_id: string | null;
    risk_points: number | null;
    reward_points: number | null;
  };
}

export interface OpenPositionRisk {
  correlation_id: string;
  direction: "long" | "short" | null;
  quantity: number | null;
  entry_price: number | null;
  sl: number | null;
  tp: number | null;
  current_price: number | null;
  unrealized_pnl: number | null;
  risk_points: number | null;
  reward_points: number | null;
  risk_dollars: number | null;
  reward_dollars: number | null;
  exposure_contracts: number | null;
  exposure_pct_of_max: number | null;
  exceeds_max_contracts: boolean;
}

export interface KillSwitchStatus {
  should_trigger: boolean;
  reasons: string[];
  enforced: boolean;
}

export interface RiskResponse {
  account_configured: boolean;
  starting_balance: number;
  current_balance: number;
  high_water_mark: number;

  daily_loss_limit: number;
  daily_realized_pnl: number;
  daily_loss_used: number;
  daily_loss_remaining: number;
  daily_loss_limit_breached: boolean;

  trailing_drawdown_limit: number;
  trailing_stop_balance: number;
  remaining_drawdown: number;
  trailing_drawdown_breached: boolean;

  max_contracts: number;
  point_value: number;

  open_position: OpenPositionRisk | null;
  kill_switch: KillSwitchStatus;
}

export interface AnalyticsSummaryResponse {
  total_trades: number;
  wins: number;
  losses: number;
  win_rate_pct: number;
  gross_profit: number;
  gross_loss: number;
  profit_factor: number | null;
  expectancy: number;
  avg_win: number | null;
  avg_loss: number | null;
  avg_r: number | null;
  r_multiple_sample_size: number;
}

export interface EquityPoint {
  correlation_id: string;
  closed_at: string;
  realized_pnl: number;
  equity: number;
  high_water_mark: number;
  drawdown: number;
  drawdown_pct: number;
}

export interface EquityCurveResponse {
  starting_balance: number;
  points: EquityPoint[];
  ending_equity: number;
  max_drawdown: number;
  max_drawdown_pct: number;
}

export interface BreakdownGroup {
  key: string;
  total_trades: number;
  wins: number;
  losses: number;
  win_rate_pct: number;
  total_realized_pnl: number;
  avg_realized_pnl: number;
}

export interface BreakdownResponse {
  by_session: BreakdownGroup[];
  by_setup: BreakdownGroup[];
  by_weekday: BreakdownGroup[];
}

export type AiNoteType = "entry_score" | "post_trade_review" | "daily_report" | "weekly_report";

// Sprint 7: one measurable factor behind a confidence score - this entry's value
// compared against the median among historically similar winners and losers. See
// atlas/intelligence.py::compute_factors. `favorable` is null when there wasn't
// enough historical data on one side (winners or losers) to compare against.
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
  // Sprint 7: only populated for note_type "entry_score" - the deterministic,
  // historically-grounded numbers computed before Claude was ever called. Null for
  // post_trade_review/daily_report/weekly_report rows, and also null on an
  // entry_score row when similar_trade_count is 0 (nothing to compute against yet).
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

// Sprint 7: on-demand recomputation of atlas/intelligence.py's snapshot - no Claude
// call, nothing persisted. Works for any trade (open or closed), unlike the
// entry_score AiNote which is a one-time snapshot taken at entry time.
export interface IntelligenceSnapshot {
  correlation_id: string;
  similar_trade_count: number;
  confidence_score: number | null;
  confidence_label: string;
  summary: AnalyticsSummaryResponse;
  factors: Factor[];
}

export type ReportPeriod = "daily" | "weekly";

// Sprint 11 - Activity Center: unified chronological feed built server-side from
// existing trades/ai_notes/risk/status data - see atlas/activity.py. Risk and system
// events are current-state snapshots, not history (see that module's docstring), so
// don't assume every past breach/error will appear here, only the most recent.
export type ActivityCategory = "trading" | "ai" | "risk" | "analytics" | "system";
export type ActivitySeverity = "info" | "success" | "warning" | "critical";

export interface ActivityEvent {
  id: string;
  timestamp: string;
  category: ActivityCategory;
  severity: ActivitySeverity;
  title: string;
  description: string | null;
  correlation_id: string | null;
}

export interface ActivityResponse {
  count: number;
  events: ActivityEvent[];
}

async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, { cache: "no-store", headers: authHeaders() });
  if (!res.ok) {
    throw new Error(`GET ${path} failed: HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}

export const api = {
  currentTrade: () => apiGet<CurrentTradeResponse>("/api/v1/trades/current"),

  tradeList: (params?: { limit?: number; status?: string }) => {
    const qs = new URLSearchParams();
    if (params?.limit) qs.set("limit", String(params.limit));
    if (params?.status) qs.set("status", params.status);
    const query = qs.toString();
    return apiGet<TradeListResponse>(`/api/v1/trades${query ? `?${query}` : ""}`);
  },

  tradeDetail: async (correlationId: string): Promise<TradeDetailResponse | null> => {
    const res = await fetch(
      `${API_BASE_URL}/api/v1/trades/${encodeURIComponent(correlationId)}`,
      { cache: "no-store", headers: authHeaders() },
    );
    if (res.status === 404) return null;
    if (!res.ok) throw new Error(`GET trade detail failed: HTTP ${res.status}`);
    return (await res.json()) as TradeDetailResponse;
  },

  status: () => apiGet<StatusResponse>("/api/v1/status"),

  statsToday: () => apiGet<StatsTodayResponse>("/api/v1/stats/today"),

  risk: () => apiGet<RiskResponse>("/api/v1/risk"),

  analyticsSummary: () => apiGet<AnalyticsSummaryResponse>("/api/v1/analytics/summary"),

  equityCurve: () => apiGet<EquityCurveResponse>("/api/v1/analytics/equity-curve"),

  breakdown: () => apiGet<BreakdownResponse>("/api/v1/analytics/breakdown"),

  aiNotes: (params?: { tradeCorrelationId?: string; noteType?: AiNoteType; limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.tradeCorrelationId) qs.set("trade_correlation_id", params.tradeCorrelationId);
    if (params?.noteType) qs.set("note_type", params.noteType);
    if (params?.limit) qs.set("limit", String(params.limit));
    const query = qs.toString();
    return apiGet<AiNotesResponse>(`/api/v1/ai/notes${query ? `?${query}` : ""}`);
  },

  aiReports: (params?: { period?: ReportPeriod; limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.period) qs.set("period", params.period);
    if (params?.limit) qs.set("limit", String(params.limit));
    const query = qs.toString();
    return apiGet<AiReportsResponse>(`/api/v1/ai/reports${query ? `?${query}` : ""}`);
  },

  triggerReport: async (period: ReportPeriod): Promise<void> => {
    const res = await fetch(
      `${API_BASE_URL}/api/v1/ai/reports/${period}`, { method: "POST", headers: authHeaders() },
    );
    if (!res.ok) throw new Error(`POST report trigger failed: HTTP ${res.status}`);
  },

  intelligence: async (correlationId: string): Promise<IntelligenceSnapshot | null> => {
    const res = await fetch(
      `${API_BASE_URL}/api/v1/ai/intelligence/${encodeURIComponent(correlationId)}`,
      { cache: "no-store", headers: authHeaders() },
    );
    if (res.status === 404) return null;
    if (!res.ok) throw new Error(`GET intelligence failed: HTTP ${res.status}`);
    return (await res.json()) as IntelligenceSnapshot;
  },

  activity: (params?: { limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.limit) qs.set("limit", String(params.limit));
    const query = qs.toString();
    return apiGet<ActivityResponse>(`/api/v1/activity${query ? `?${query}` : ""}`);
  },
};
