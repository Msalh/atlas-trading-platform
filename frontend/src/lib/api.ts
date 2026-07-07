// Typed client for the Atlas backend's versioned REST API (atlas/api/v1/*.py).
// These shapes are hand-mirrored from the FastAPI handlers, which return plain dicts
// rather than Pydantic models - keep this file in sync if a backend response shape
// changes.

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

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
}

export type TimelineEventType =
  | "entry_received"
  | "pmt_forwarded"
  | "pmt_forward_failed"
  | "ai_analysis"
  | "price_update"
  | "exit";

export interface TimelineEvent {
  type: TimelineEventType;
  at: string | null;
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

async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, { cache: "no-store" });
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
      { cache: "no-store" },
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
};
