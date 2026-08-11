"""Exact public allowlist for GET /api/v1/trader-now/results."""

from dataclasses import dataclass

SHADOW_RESULTS_SCHEMA_VERSION = "trader_now_results.v1"


@dataclass(frozen=True)
class HealthResult:
    status: str
    database_status: str


@dataclass(frozen=True)
class ShadowPhaseResult:
    phase: str
    certification_status: str
    certification_basis: str


@dataclass(frozen=True)
class MarketStateResult:
    count: int
    latest_timestamp: str | None


@dataclass(frozen=True)
class StoredSignalResult:
    count: int
    latest_correlation_id: str | None
    latest_timestamp: str | None


@dataclass(frozen=True)
class StrategyResult:
    availability: str
    semantic_label: str
    disposition: str | None
    direction: str | None
    reason_codes: tuple[str, ...]
    confidence: float | None
    timestamp: str | None


@dataclass(frozen=True)
class RiskResult:
    availability: str
    status: str | None


@dataclass(frozen=True)
class DecisionResult:
    availability: str
    state: None


@dataclass(frozen=True)
class AiNoteResult:
    system: str
    phase_18_ai_analysis: str
    stored_count: int
    latest_status: str
    latest_note_type: str | None
    latest_score: int | None
    latest_score_label: str | None
    latest_correlation_id: str | None
    latest_timestamp: str | None
    free_text_exposed: bool


@dataclass(frozen=True)
class IngestionTelemetryResult:
    duplicate_webhooks: int
    rejected_webhooks: int


@dataclass(frozen=True)
class ProcessTelemetryResult:
    scope: str
    limitation: str
    reset_at: str
    authentication_failures: int
    http_5xx_responses: int
    runtime_errors: int
    ingestion: IngestionTelemetryResult


@dataclass(frozen=True)
class ExecutionSafetyResult:
    pickmytrade_configured: bool
    execution_disabled: bool
    current_authority: str
    historical_pickmytrade_forwarded_records: int
    historical_records_are_current_authority: bool


@dataclass(frozen=True)
class ShadowResultsResponse:
    schema_version: str
    generated_at: str
    health: HealthResult
    shadow: ShadowPhaseResult
    market_state: MarketStateResult
    stored_strategy_signals: StoredSignalResult
    strategy: StrategyResult
    risk: RiskResult
    decision: DecisionResult
    ai_note: AiNoteResult
    telemetry: ProcessTelemetryResult
    execution_safety: ExecutionSafetyResult
