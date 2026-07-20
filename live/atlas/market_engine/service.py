"""
Market Engine services - the ingest service (Sprint 3) and the read service
(Sprint 4). Orchestration only in both cases: routes stay thin, this module
does the work that's worth unit-testing independent of HTTP.

Deliberately does not know about authentication, rate limiting, or the raw
HTTP request - those are atlas.api.v1.market_state.py's concern (the transport
boundary).
"""
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from pydantic import ValidationError

from atlas.core.errors import AtlasDomainError
from atlas.core.primitives import Price, Symbol, Timeframe
from atlas.market_engine.adapters.tradingview.translator import to_canonical
from atlas.market_engine.adapters.tradingview.wire_models import TradingViewMarketStatePayload
from atlas.market_engine.models import MarketState
from atlas.market_engine.ports import IngestOutcome, MarketStateRepository


@dataclass(frozen=True)
class IngestResult:
    """`outcome` is None exactly when `error` is set - the payload never
    reached the repository. Both are never set at once, and never both unset.

    `error_stage`/`error_exception_type` are set alongside `error` (added for
    the market-state 422 diagnostic logging) - which of the two validation
    stages rejected the payload, and the exception's class name, so the
    caller can log a machine-filterable rejection reason without having to
    parse `error`'s free-text string."""

    outcome: Optional[IngestOutcome] = None
    error: Optional[str] = None
    error_stage: Optional[str] = None
    error_exception_type: Optional[str] = None


async def ingest_tradingview_payload(
    raw_json: dict[str, Any], raw_payload: str, repository: MarketStateRepository
) -> IngestResult:
    try:
        payload = TradingViewMarketStatePayload.model_validate(raw_json)
    except ValidationError as e:
        return IngestResult(
            error=f"invalid payload: {e.errors(include_context=False)}",
            error_stage="wire_model_validation",
            error_exception_type=type(e).__name__,
        )

    try:
        state = to_canonical(payload)
    except AtlasDomainError as e:
        return IngestResult(
            error=str(e), error_stage="domain_translation", error_exception_type=type(e).__name__,
        )

    outcome = await repository.ingest(state, raw_payload=raw_payload)
    return IngestResult(outcome=outcome)


def _price_value(price: Optional[Price]) -> Optional[float]:
    return None if price is None else price.value


def market_state_to_dict(state: MarketState) -> dict[str, Any]:
    """Shapes a canonical MarketState into a JSON-serializable dict for the
    read API - the read-side analogue of translator.to_canonical(), except
    this direction is not vendor-specific (there's only one shape for API
    responses, regardless of which adapter originally wrote the data), so it
    lives here rather than under adapters/. Always includes received_at, which
    the TradingView wire payload never carries - it's information this system
    adds, not something any adapter's wire format determines."""
    return {
        "schema_version": state.schema_version,
        "event_id": state.envelope.event_id,
        "symbol": state.symbol.ticker,
        "source": state.envelope.source,
        "timeframe": state.timeframe.value,
        "timestamp": state.envelope.occurred_at.isoformat(),
        "received_at": state.envelope.received_at.isoformat(),
        "bar_status": state.bar_status.value,
        "event_type": state.event_type.value,
        "open": _price_value(state.open),
        "high": _price_value(state.high),
        "low": _price_value(state.low),
        "close": _price_value(state.close),
        "volume": state.volume,
        "session_name": state.session_name.value if state.session_name is not None else None,
        "is_rth": state.is_rth,
        "trading_date": state.trading_date.isoformat() if state.trading_date is not None else None,
        "rth_open": _price_value(state.rth_open),
        "previous_day_high": _price_value(state.previous_day_high),
        "previous_day_low": _price_value(state.previous_day_low),
        "overnight_high": _price_value(state.overnight_high),
        "overnight_low": _price_value(state.overnight_low),
        "vwap": _price_value(state.vwap),
        "distance_from_vwap_points": state.distance_from_vwap_points,
        "atr": state.atr,
        "volume_ratio": state.volume_ratio,
        "nearest_liquidity_level": _price_value(state.nearest_liquidity_level),
        "nearest_liquidity_type": state.nearest_liquidity_type,
        "distance_to_liquidity_ticks": state.distance_to_liquidity_ticks,
        "overnight_high_status": state.overnight_high_status,
        "overnight_low_status": state.overnight_low_status,
        "previous_day_high_status": state.previous_day_high_status,
        "previous_day_low_status": state.previous_day_low_status,
        "trend_1m": state.trend_1m,
        "trend_5m": state.trend_5m,
        "trend_15m": state.trend_15m,
        "trend_1h": state.trend_1h,
        "liquidity_sweep": state.liquidity_sweep,
        "reclaim": state.reclaim,
        "rejection": state.rejection,
        "displacement": state.displacement,
        "volume_spike": state.volume_spike,
    }


async def get_latest_market_state(
    symbol: Symbol, timeframe: Timeframe, repository: MarketStateRepository
) -> Optional[dict[str, Any]]:
    state = await repository.get_latest(symbol, timeframe)
    return None if state is None else market_state_to_dict(state)


async def get_market_state_history(
    symbol: Symbol, timeframe: Timeframe, limit: int, repository: MarketStateRepository
) -> list[dict[str, Any]]:
    states = await repository.get_history(symbol, timeframe, limit)
    return [market_state_to_dict(s) for s in states]


def find_gaps(states: list[MarketState], timeframe: Timeframe) -> list[dict[str, Any]]:
    """Sprint 8 (Data Validation & Integrity). Pure function: given a list of
    MarketState for one (symbol, timeframe) series, in any order, flags every
    consecutive pair (by occurred_at) whose spacing exceeds 1.5x the
    timeframe's expected duration - a buffer against normal jitter, the same
    reasoning atlas/monitoring.py's staleness threshold already used (Sprint 7).

    Deliberately does NOT know about expected market-closed periods (weekends,
    the daily maintenance window) - a raw report, not a judgment. Every
    Friday-close-to-Sunday-open span will appear here as a large gap. A human
    reading this report is expected to recognize that, the same disclosed-
    limitation pattern atlas/monitoring.py already established for market-hours
    awareness (see its docstring) - not solved here, and not silently assumed
    away either."""
    ordered = sorted(states, key=lambda s: s.envelope.occurred_at)
    expected_minutes = timeframe.duration_minutes
    tolerance_minutes = expected_minutes * 1.5
    gaps = []
    for previous, current in zip(ordered, ordered[1:]):
        actual_minutes = (current.envelope.occurred_at - previous.envelope.occurred_at).total_seconds() / 60
        if actual_minutes > tolerance_minutes:
            gaps.append({
                "after": previous.envelope.occurred_at.isoformat(),
                "before": current.envelope.occurred_at.isoformat(),
                "expected_interval_minutes": expected_minutes,
                "actual_gap_minutes": round(actual_minutes, 2),
                "estimated_missing_bars": round(actual_minutes / expected_minutes) - 1,
            })
    return gaps


async def get_market_state_integrity_report(
    symbol: Symbol, timeframe: Timeframe, limit: int, repository: MarketStateRepository
) -> dict[str, Any]:
    """Detection and reporting only - no backfill, no repair. Reuses
    get_history rather than a new repository method: the data this needs
    (a bounded, ordered slice of one series) is exactly what get_history
    already returns."""
    states = await repository.get_history(symbol, timeframe, limit)
    gaps = find_gaps(states, timeframe)
    return {
        "symbol": symbol.ticker,
        "timeframe": timeframe.value,
        "checked_count": len(states),
        "gap_count": len(gaps),
        "gaps": gaps,
    }


async def get_market_state_export(
    symbol: Symbol, timeframe: Timeframe, start: datetime, end: datetime, limit: int, repository: MarketStateRepository
) -> dict[str, Any]:
    """Sprint 9 (Dataset Builder, Phase 1). A static, static-in-time export of
    a stored series over [start, end] - detection and reporting only, same as
    get_market_state_integrity_report: no repair, no backfill, no automation.

    Gaps are surfaced inline (`gap_count`/`gaps`) rather than requiring a
    second call to /market-state/integrity, because that endpoint's `limit`
    parameter means "most recent N" - it has no way to describe the same
    [start, end] window an export covers, so it cannot be relied on to check
    the same range being exported. `data` is a JSON array (not a JSONL/CSV
    file body) so this reuses the exact response-envelope convention every
    other read endpoint in this file already uses, rather than inventing a
    new transport/content-type for this Sprint - a caller wanting a literal
    file saves this response's `data` field directly. Revisit only if a real
    Dataset Builder consumer's export sizes make a JSON array unwieldy - not
    guessed at now."""
    states = await repository.get_range(symbol, timeframe, start, end, limit)
    gaps = find_gaps(states, timeframe)
    return {
        "symbol": symbol.ticker,
        "timeframe": timeframe.value,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "count": len(states),
        "gap_count": len(gaps),
        "gaps": gaps,
        "data": [market_state_to_dict(s) for s in states],
    }


async def replay_market_state(
    symbol: Symbol, timeframe: Timeframe, start: datetime, end: datetime,
    limit: int, repository: MarketStateRepository,
) -> AsyncIterator[MarketState]:
    """Sprint 10 (Replay Engine, Phase 1). Deterministically re-delivers a
    stored series, in exact occurred_at order, to a caller.

    Deliberately yields raw MarketState domain objects, NOT dicts -
    market_state_to_dict (used by every other function in this module) shapes
    data for JSON transport, which is the right choice for an HTTP read
    endpoint but the wrong one for Replay: Replay's actual purpose is to feed
    a future in-process consumer (Phase 3's AI/strategy validation harness)
    real domain objects to operate on directly, the same objects live
    ingestion produces. Keeping this function's contract as "an async stream
    of MarketState" - not "an async stream of JSON-ready dicts" - is what
    keeps Replay a domain capability rather than an HTTP-shaped one; nothing
    about this function knows FastAPI, JSON, or HTTP exists, and this Sprint
    deliberately does not add a route in front of it (see this Sprint's own
    review for why: no real consumer exists yet, so no consumer-interface
    design work is done speculatively ahead of Phase 3 actually needing one).

    Internally still a single bounded get_range call, not a true
    database-level streaming cursor - the generator shape is Phase 1's
    correct CONSUMER contract, not a claim about how the data is fetched
    underneath it. Real streaming from Postgres is a future optimization,
    justified only once a measured need for it exists."""
    states = await repository.get_range(symbol, timeframe, start, end, limit)
    for state in states:
        yield state
