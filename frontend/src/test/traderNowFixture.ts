import type { TraderNowResponse } from "@/lib/traderNowApi";

const available = { status: "available", reason_codes: [] };

export function traderNowFixture(overrides: Partial<TraderNowResponse> = {}): TraderNowResponse {
  return {
    schema_version: "trader_now_response.v2",
    domain_schema_version: "trader_now.v1",
    snapshot_id: null,
    evaluated_at: "2026-07-26T12:00:00Z",
    input_snapshot_at: "2026-07-26T11:55:00Z",
    identity: { product: "MNQ", symbol: "MNQ1!", timeframe: "5m", strategy_id: "displacement_volume_context", strategy_version: "strategy.v1" },
    trust: { status: "trusted", policy_version: "freshness.v1", reason_codes: [] },
    availability: {
      market: available, market_history: available, rules: available, setups: available,
      context: available, interpretations: available, strategy: available,
    },
    market: {
      availability: available, history_availability: available,
      economic_instrument: { symbol: "MNQ" },
      market_data_series: { provider: "tradingview", symbol: "MNQ1!", series_type: "continuous", resolved_at: "2026-07-26T12:00:00Z", resolution_version: "tradingview-mnq1.v1" },
      listed_instrument: null, observed_at: "2026-07-26T11:55:02Z", latest_closed_at: "2026-07-26T11:55:00Z",
      bar_count: 288, source_schema_versions: ["market_state.v1"],
      latest_bar: {
        occurred_at: "2026-07-26T11:55:00Z", received_at: "2026-07-26T11:55:02Z",
        schema_version: "market_state.v1", symbol: "MNQ1!", timeframe: "5m",
        open: { value: 20100, tick_size: 0.25 }, high: { value: 20105, tick_size: 0.25 },
        low: { value: 20095, tick_size: 0.25 }, close: { value: 20102, tick_size: 0.25 },
        volume: 1200, volume_ratio: 1.4, atr: 18.5, session_name: "rth", is_rth: true,
      },
    },
    source_trust: {
      freshness: { status: "current", policy_version: "freshness.v1", evaluated_at: "2026-07-26T12:00:00Z",
        expected_close_at: "2026-07-26T11:55:00Z", latest_closed_at: "2026-07-26T11:55:00Z", lateness_seconds: 0, reason_codes: [] },
      availability: "available", structural_validity: "valid", overall: "trusted", reason_codes: [],
    },
    rules: { availability: available, schema_version: "rule_engine.v1", symbol: "MNQ1!", timeframe: "5m",
      occurred_at: "2026-07-26T11:55:00Z", facts: [
        { fact_id: "displacement_up", status: "computed", definition_version: "rule.v1", value: true, reason: null },
      ] },
    setups: { availability: available, schema_version: "setup_engine.v1", symbol: "MNQ1!", timeframe: "5m",
      occurred_at: "2026-07-26T11:55:00Z", setups: [
        { setup_id: "continuation", status: "computed", definition_version: "setup.v1", detected: true,
          severity: "medium", reason: null, supporting_fact_ids: ["displacement_up"] },
      ] },
    context: { availability: available, data: {
      symbol: "MNQ1!", timeframe: "5m", occurred_at: "2026-07-26T11:55:00Z",
      session: { phase: "regular", session_open_at: "2026-07-26T08:30:00Z", session_close_at: "2026-07-26T15:00:00Z",
        minutes_since_session_open: 205, minutes_until_session_close: 185, upstream_session_name: "rth", upstream_is_rth: true, drift_status: "aligned" },
      volatility: { regime: "normal", atr_percentile_rank: 0.62, lookback_bars_used: 100 },
      quality: "good", classifier_version: "context.v1", calendar_version: "cme.v1", context_fingerprint: "context-fingerprint",
    } },
    interpretations: { availability: available, interpretations: [{
      occurred_at: "2026-07-26T11:55:00Z", setup_id: "continuation", detected: true, direction: "long",
      source: "setup", source_fact_ids: ["displacement_up"], reason_codes: ["continuation_confirmed"],
      interpretation_version: "interpretation.v1", interpretation_fingerprint: "interpretation-fingerprint",
    }] },
    strategy: { availability: available, decisions: [{
      occurred_at: "2026-07-26T11:55:00Z", strategy_id: "displacement_volume_context", strategy_version: "strategy.v1",
      disposition: "candidate", direction: "long", setup_ids: ["continuation"], reason_codes: ["candidate_conditions_met"],
      context_fingerprint: "context-fingerprint", invalidation: null, stop: null, target: null, confidence: 0.8,
    }] },
    risk: null,
    decision: { availability: "not_implemented", state: null },
    ...overrides,
  };
}
