"""Read-only aggregation for the Shadow Results API."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from atlas.api_models.shadow_results import (
    SHADOW_RESULTS_SCHEMA_VERSION,
    AiNoteResult,
    DecisionResult,
    ExecutionSafetyResult,
    HealthResult,
    IngestionTelemetryResult,
    MarketStateResult,
    ProcessTelemetryResult,
    RiskResult,
    ShadowPhaseResult,
    ShadowResultsResponse,
    StoredSignalResult,
    StrategyResult,
)
from atlas.api_models.trader_now import TraderNowResponse
from atlas.core.primitives import Symbol, Timeframe
from atlas.market_engine.ports import MarketStateRepository
from atlas.repositories.base import TradeRepository
from atlas.shadow_results.telemetry import ProcessTelemetry


def _timestamp(value: datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _latest_ai_status(note: dict[str, Any] | None) -> str:
    if note is None:
        return "unavailable"
    if note.get("error"):
        return "failed"
    return "recorded"


async def build_shadow_results(
    *,
    repository: TradeRepository,
    market_repository: MarketStateRepository,
    trader_now: TraderNowResponse,
    telemetry: ProcessTelemetry,
    market_symbol: str,
    market_timeframe: str,
    pickmytrade_configured: bool,
    now: datetime | None = None,
) -> ShadowResultsResponse:
    """Build a fresh allowlisted response without returning stored payload fields."""
    generated_at = now or datetime.now(timezone.utc)
    database_ok = True
    try:
        await repository.ping()
    except Exception:  # noqa: BLE001 - database drivers are sanitized here
        database_ok = False

    counts = await repository.shadow_result_counts()
    latest_signals = await repository.list_recent(limit=1)
    latest_signal = latest_signals[0] if latest_signals else None
    latest_notes = await repository.list_ai_notes(limit=1)
    latest_note = latest_notes[0] if latest_notes else None
    symbol = Symbol(market_symbol)
    timeframe = Timeframe(market_timeframe)
    market_count = await market_repository.count(symbol, timeframe)
    latest_market = await market_repository.get_latest(symbol, timeframe)

    strategy_decision = (
        trader_now.strategy.decisions[0] if trader_now.strategy.decisions else None
    )
    telemetry_snapshot = telemetry.snapshot()
    return ShadowResultsResponse(
        schema_version=SHADOW_RESULTS_SCHEMA_VERSION,
        generated_at=_timestamp(generated_at) or "",
        health=HealthResult(
            status="healthy" if database_ok else "degraded",
            database_status="healthy" if database_ok else "unavailable",
        ),
        shadow=ShadowPhaseResult(
            phase="shadow_observation",
            certification_status="pending",
            certification_basis="not_recorded_by_runtime",
        ),
        market_state=MarketStateResult(
            count=market_count,
            latest_timestamp=(
                _timestamp(latest_market.envelope.occurred_at)
                if latest_market is not None
                else None
            ),
        ),
        stored_strategy_signals=StoredSignalResult(
            count=counts.strategy_signals,
            latest_correlation_id=(
                str(latest_signal["correlation_id"]) if latest_signal else None
            ),
            latest_timestamp=(
                _timestamp(latest_signal.get("received_at")) if latest_signal else None
            ),
        ),
        strategy=StrategyResult(
            availability=trader_now.strategy.availability.status,
            semantic_label="opportunity_evaluation_not_recommendation",
            disposition=(strategy_decision.disposition if strategy_decision else None),
            direction=strategy_decision.direction if strategy_decision else None,
            reason_codes=(
                strategy_decision.reason_codes
                if strategy_decision
                else trader_now.strategy.availability.reason_codes
            ),
            confidence=strategy_decision.confidence if strategy_decision else None,
            timestamp=strategy_decision.occurred_at if strategy_decision else None,
        ),
        risk=RiskResult(
            availability="available" if trader_now.risk is not None else "unavailable",
            status=trader_now.risk.status if trader_now.risk is not None else None,
        ),
        decision=DecisionResult(
            availability=trader_now.decision.availability,
            state=None,
        ),
        ai_note=AiNoteResult(
            system="legacy_claude_copilot",
            phase_18_ai_analysis="not_integrated",
            stored_count=counts.ai_notes,
            latest_status=_latest_ai_status(latest_note),
            latest_note_type=latest_note.get("note_type") if latest_note else None,
            latest_score=latest_note.get("score") if latest_note else None,
            latest_score_label=(
                latest_note.get("score_label") if latest_note else None
            ),
            latest_correlation_id=(
                latest_note.get("trade_correlation_id") if latest_note else None
            ),
            latest_timestamp=(
                _timestamp(latest_note.get("created_at")) if latest_note else None
            ),
            free_text_exposed=False,
        ),
        telemetry=ProcessTelemetryResult(
            scope="current_process",
            limitation="resets_on_process_restart_or_deployment",
            reset_at=_timestamp(telemetry_snapshot.reset_at) or "",
            authentication_failures=telemetry_snapshot.authentication_failures,
            http_5xx_responses=telemetry_snapshot.http_5xx_responses,
            runtime_errors=telemetry_snapshot.runtime_errors,
            ingestion=IngestionTelemetryResult(
                duplicate_webhooks=telemetry_snapshot.duplicate_webhooks,
                rejected_webhooks=telemetry_snapshot.rejected_webhooks,
            ),
        ),
        execution_safety=ExecutionSafetyResult(
            pickmytrade_configured=pickmytrade_configured,
            execution_disabled=not pickmytrade_configured,
            current_authority=(
                "unexpected_execution_configuration"
                if pickmytrade_configured
                else "execution_not_authorized"
            ),
            historical_pickmytrade_forwarded_records=(
                counts.historically_pickmytrade_forwarded
            ),
            historical_records_are_current_authority=False,
        ),
    )
