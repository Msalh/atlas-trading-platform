import { ApiFetchError, proxyGet } from "@/lib/proxyClient";

export { ApiFetchError };

export interface Availability { status: string; reason_codes: string[] }
export interface Price { value: number; tick_size: number }
export interface TraderNowResponse {
  schema_version: "trader_now_response.v2";
  domain_schema_version: string;
  snapshot_id: string | null;
  evaluated_at: string | null;
  input_snapshot_at: string | null;
  identity: { product: string; symbol: string; timeframe: string; strategy_id: string; strategy_version: string };
  trust: { status: string; policy_version: string; reason_codes: string[] };
  availability: Record<string, Availability>;
  market: {
    availability: Availability; history_availability: Availability;
    economic_instrument: { symbol: string } | null;
    market_data_series: { provider: string; symbol: string; series_type: string; resolved_at: string; resolution_version: string } | null;
    listed_instrument: { venue: string; contract_symbol: string; expiry: string } | null;
    observed_at: string | null; latest_closed_at: string | null; bar_count: number;
    source_schema_versions: string[];
    latest_bar: null | { occurred_at: string; received_at: string; schema_version: string; symbol: string; timeframe: string;
      open: Price; high: Price; low: Price; close: Price; volume: number; volume_ratio: number | null;
      atr: number | null; session_name: string | null; is_rth: boolean | null };
  };
  source_trust: null | { freshness: { status: string; policy_version: string; evaluated_at: string;
    expected_close_at: string | null; latest_closed_at: string | null; lateness_seconds: number | null;
    reason_codes: string[] }; availability: string; structural_validity: string; overall: string; reason_codes: string[] };
  rules: { availability: Availability; schema_version: string | null; symbol: string | null; timeframe: string | null;
    occurred_at: string | null; facts: Array<{ fact_id: string; status: string; definition_version: string;
      value: boolean | string | null; reason: string | null }> };
  setups: { availability: Availability; schema_version: string | null; symbol: string | null; timeframe: string | null;
    occurred_at: string | null; setups: Array<{ setup_id: string; status: string; definition_version: string;
      detected: boolean | null; severity: string | null; reason: string | null; supporting_fact_ids: string[] }> };
  context: { availability: Availability; data: null | { symbol: string; timeframe: string; occurred_at: string;
    session: { phase: string; session_open_at: string | null; session_close_at: string | null;
      minutes_since_session_open: number | null; minutes_until_session_close: number | null;
      upstream_session_name: string | null; upstream_is_rth: boolean | null; drift_status: string };
    volatility: { regime: string; atr_percentile_rank: number | null; lookback_bars_used: number };
    quality: string; classifier_version: string; calendar_version: string; context_fingerprint: string } };
  interpretations: { availability: Availability; interpretations: Array<{ occurred_at: string; setup_id: string;
    detected: boolean; direction: string; source: string; source_fact_ids: string[]; reason_codes: string[];
    interpretation_version: string; interpretation_fingerprint: string }> };
  strategy: { availability: Availability; decisions: Array<{ occurred_at: string; strategy_id: string;
    strategy_version: string; disposition: "candidate" | "rejected" | "no_signal"; direction: string;
    setup_ids: string[]; reason_codes: string[]; context_fingerprint: string; invalidation: Price | null;
    stop: Price | null; target: Price | null; confidence: number | null }> };
  risk: null | { schema_version: string; assessment_id: string; policy_id: string | null; policy_version: string | null;
    assessed_at: string; candidate_at: string; status: string; primary_reason: string | null;
    contributing_reasons: string[]; sizing_mode: string | null; requested_quantity: number | null;
    maximum_approved_quantity: number | null; approved_quantity: number | null; risk_ticks: number | null;
    risk_dollars_per_contract: string | null; approved_total_candidate_risk: string | null;
    remaining_daily_risk_capacity: string | null; remaining_drawdown_capacity: string | null;
    exposure_before: number | null; exposure_after: number | null; account_freshness: string;
    position_freshness: string; candidate_freshness: string; reconciliation_status: string | null;
    has_delayed_data: boolean };
  decision: { availability: string; state: null };
}

type Obj = Record<string, unknown>;
type Validator = (value: unknown) => boolean;
const obj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);
const str: Validator = (v) => typeof v === "string";
const num: Validator = (v) => typeof v === "number" && Number.isFinite(v);
const bool: Validator = (v) => typeof v === "boolean";
const factValue: Validator = (v) => v === null || typeof v === "boolean" || typeof v === "string";
const nil: Validator = (v) => v === null;
const nullable = (check: Validator): Validator => (v) => v === null || check(v);
const array = (check: Validator): Validator => (v) => Array.isArray(v) && v.every(check);
const oneOf = (...values: unknown[]): Validator => (v) => values.includes(v);
const record = (check: Validator): Validator => (v) => obj(v) && Object.values(v).every(check);
const shape = (fields: Record<string, Validator>): Validator => (v) => {
  if (!obj(v)) return false;
  const keys = Object.keys(fields);
  return Object.keys(v).length === keys.length && keys.every((key) => key in v && fields[key](v[key]));
};

const availability = shape({ status: str, reason_codes: array(str) });
const price = shape({ value: num, tick_size: num });
const identity = shape({ product: str, symbol: str, timeframe: str, strategy_id: str, strategy_version: str });
const trust = shape({ status: str, policy_version: str, reason_codes: array(str) });
const market = shape({
  availability, history_availability: availability,
  economic_instrument: nullable(shape({ symbol: str })),
  market_data_series: nullable(shape({ provider: str, symbol: str, series_type: str, resolved_at: str, resolution_version: str })),
  listed_instrument: nullable(shape({ venue: str, contract_symbol: str, expiry: str })),
  observed_at: nullable(str), latest_closed_at: nullable(str), bar_count: num, source_schema_versions: array(str),
  latest_bar: nullable(shape({ occurred_at: str, received_at: str, schema_version: str, symbol: str, timeframe: str,
    open: price, high: price, low: price, close: price, volume: num, volume_ratio: nullable(num),
    atr: nullable(num), session_name: nullable(str), is_rth: nullable(bool) })),
});
const sourceTrust = nullable(shape({
  freshness: shape({ status: str, policy_version: str, evaluated_at: str, expected_close_at: nullable(str),
    latest_closed_at: nullable(str), lateness_seconds: nullable(num), reason_codes: array(str) }),
  availability: str, structural_validity: str, overall: str, reason_codes: array(str),
}));
const rules = shape({ availability, schema_version: nullable(str), symbol: nullable(str), timeframe: nullable(str),
  occurred_at: nullable(str), facts: array(shape({ fact_id: str, status: str, definition_version: str,
    value: factValue, reason: nullable(str) })) });
const setups = shape({ availability, schema_version: nullable(str), symbol: nullable(str), timeframe: nullable(str),
  occurred_at: nullable(str), setups: array(shape({ setup_id: str, status: str, definition_version: str,
    detected: oneOf(null, true, false), severity: nullable(str), reason: nullable(str), supporting_fact_ids: array(str) })) });
const context = shape({ availability, data: nullable(shape({ symbol: str, timeframe: str, occurred_at: str,
  session: shape({ phase: str, session_open_at: nullable(str), session_close_at: nullable(str),
    minutes_since_session_open: nullable(num), minutes_until_session_close: nullable(num),
    upstream_session_name: nullable(str), upstream_is_rth: nullable(bool), drift_status: str }),
  volatility: shape({ regime: str, atr_percentile_rank: nullable(num), lookback_bars_used: num }),
  quality: str, classifier_version: str, calendar_version: str, context_fingerprint: str })) });
const interpretations = shape({ availability, interpretations: array(shape({ occurred_at: str, setup_id: str,
  detected: bool, direction: str, source: str, source_fact_ids: array(str), reason_codes: array(str),
  interpretation_version: str, interpretation_fingerprint: str })) });
const strategy = shape({ availability, decisions: array(shape({ occurred_at: str, strategy_id: str,
  strategy_version: str, disposition: oneOf("candidate", "rejected", "no_signal"), direction: str,
  setup_ids: array(str), reason_codes: array(str), context_fingerprint: str, invalidation: nullable(price),
  stop: nullable(price), target: nullable(price), confidence: nullable(num) })) });
const risk = nullable(shape({
  schema_version: str, assessment_id: str, policy_id: nullable(str), policy_version: nullable(str),
  assessed_at: str, candidate_at: str, status: str, primary_reason: nullable(str), contributing_reasons: array(str),
  sizing_mode: nullable(str), requested_quantity: nullable(num), maximum_approved_quantity: nullable(num),
  approved_quantity: nullable(num), risk_ticks: nullable(num), risk_dollars_per_contract: nullable(str),
  approved_total_candidate_risk: nullable(str), remaining_daily_risk_capacity: nullable(str),
  remaining_drawdown_capacity: nullable(str), exposure_before: nullable(num), exposure_after: nullable(num),
  account_freshness: str, position_freshness: str, candidate_freshness: str,
  reconciliation_status: nullable(str), has_delayed_data: bool,
}));

const traderNow = shape({
  schema_version: oneOf("trader_now_response.v2"), domain_schema_version: str, snapshot_id: nullable(str),
  evaluated_at: nullable(str), input_snapshot_at: nullable(str), identity, trust, availability: record(availability),
  market, source_trust: sourceTrust, rules, setups, context, interpretations, strategy, risk,
  decision: shape({ availability: str, state: nil }),
});

export function isTraderNowResponse(value: unknown): value is TraderNowResponse {
  return traderNow(value);
}

export function fetchTraderNow(): Promise<TraderNowResponse> {
  return proxyGet("trader-now", {
    symbol: "MNQ",
    timeframe: "5m",
    strategy_id: "displacement_volume_context",
  }, isTraderNowResponse);
}
