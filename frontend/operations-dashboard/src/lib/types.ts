export interface OperationsStatus {
  service: { status: string; started_at: string; uptime_seconds: number };
  build: {
    commit: string; release_tag: string; build_timestamp: string;
    response_schema_version: string; domain_schema_version: string;
  };
  database: {
    ready: boolean; transaction_read_only: boolean;
    pool_status: string; latest_probe_duration_ms: number;
  };
  requests: {
    last_success_at: string | null; last_response_duration_ms: number | null;
  };
}

export interface TraderNowStatus {
  evaluated_at: string | null;
  identity: { product: string; strategy_id: string; strategy_version: string };
  availability: Record<string, { status: string; reason_codes: string[] }>;
  market: {
    availability: { status: string; reason_codes: string[] };
    economic_instrument: { symbol: string } | null;
    market_data_series: { provider: string; symbol: string; series_type: string } | null;
    latest_closed_at: string | null;
    bar_count: number;
  };
  source_trust: {
    freshness: { status: string; lateness_seconds: number | null };
  } | null;
  rules: {
    facts: Array<{ fact_id: string; value: boolean | string | null }>;
  };
  interpretations: {
    interpretations: Array<{
      setup_id: string; direction: string; reason_codes: string[];
    }>;
  };
  strategy: {
    decisions: Array<{
      strategy_id: string; strategy_version: string; reason_codes: string[];
      confidence: number | null;
    }>;
  };
}

export interface DashboardSnapshot {
  health: { ok: boolean; service: string };
  readiness: { ok: boolean; service?: string; code?: string };
  latest: TraderNowStatus;
  operations: OperationsStatus;
  correlationId: string | null;
}
