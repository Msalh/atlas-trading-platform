"""Pure deterministic P2B-1 planner. It has no runtime integration."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

from atlas.core.primitives import Price
from atlas.risk_assessment.models import SourceProvenance
from atlas.strategy_engine.models import (
    StrategyDirection,
    StrategyDisposition,
)
from atlas.trade_risk_authority.models import (
    AuthorityMetadata,
    ProposedTrade,
    QuantityResolution,
    SourceAuthority,
    StrategyCandidateIdentity,
)
from atlas.trader_now.models import MarketDataSeriesType

from .models import (
    EvidenceAvailability,
    TradePlanInput,
    TradePlanRefusal,
    TradePlanRefusalReason,
    TradePlanResult,
    TradePlanStatus,
    TradePlanSuccess,
)
from .serialization import sha256_identity


def _ticks(value: Decimal, tick: Decimal, rounding: str) -> Decimal:
    return (value / tick).to_integral_value(rounding=rounding) * tick


def _price(value: Decimal, tick: Decimal) -> Price:
    return Price(float(value), float(tick))


def _append(reasons: list[TradePlanRefusalReason], reason: TradePlanRefusalReason) -> None:
    if reason not in reasons:
        reasons.append(reason)


@dataclass(frozen=True)
class _Geometry:
    entry: Decimal
    invalidation: Decimal
    stop: Decimal
    target: Decimal


def _geometry(value: TradePlanInput) -> _Geometry:
    assert value.policy is not None
    assert value.instrument_specification is not None
    tick = value.instrument_specification.tick_size
    bar = value.evidence.candidate_bar
    multiple = value.policy.reward_multiple
    if value.strategy.direction == StrategyDirection.LONG:
        entry = _ticks(bar.high + tick, tick, ROUND_CEILING)
        invalidation = _ticks(bar.low, tick, ROUND_FLOOR)
        stop = _ticks(invalidation - tick, tick, ROUND_FLOOR)
        target = _ticks(entry + ((entry - stop) * multiple), tick, ROUND_FLOOR)
    else:
        entry = _ticks(bar.low - tick, tick, ROUND_FLOOR)
        invalidation = _ticks(bar.high, tick, ROUND_CEILING)
        stop = _ticks(invalidation + tick, tick, ROUND_CEILING)
        target = _ticks(entry - ((stop - entry) * multiple), tick, ROUND_CEILING)
    return _Geometry(entry, invalidation, stop, target)


def _refusal(value: TradePlanInput, reasons: list[TradePlanRefusalReason]) -> TradePlanResult:
    return TradePlanResult(
        status=TradePlanStatus.REFUSED,
        success=None,
        refusal=TradePlanRefusal(tuple(reasons), value.evaluated_at),
    )


def build_trade_plan(value: TradePlanInput) -> TradePlanResult:
    """Return one complete proposal or a closed refusal; never partial geometry."""

    reasons: list[TradePlanRefusalReason] = []
    stage_reasons = (
        ("rules", TradePlanRefusalReason.RULES_UNAVAILABLE),
        ("setups", TradePlanRefusalReason.SETUPS_UNAVAILABLE),
        ("interpretation", TradePlanRefusalReason.INTERPRETATION_UNAVAILABLE),
        ("context", TradePlanRefusalReason.CONTEXT_UNAVAILABLE),
    )
    for field, reason in stage_reasons:
        if getattr(value.evidence, field) != EvidenceAvailability.AVAILABLE:
            _append(reasons, reason)
    if value.strategy.disposition != StrategyDisposition.CANDIDATE:
        _append(reasons, TradePlanRefusalReason.STRATEGY_NOT_CANDIDATE)
    if any(
        item is not None
        for item in (value.strategy.invalidation, value.strategy.stop, value.strategy.target)
    ):
        _append(reasons, TradePlanRefusalReason.STRATEGY_GEOMETRY_CONFLICT)

    try:
        candidate = StrategyCandidateIdentity.from_decision(value.strategy)
    except ValueError:
        candidate = None
    bar = value.evidence.candidate_bar
    market = value.evidence.market_input
    if (
        candidate is None
        or candidate != value.evidence.candidate
        or candidate.occurred_at != bar.source_event.occurred_at
        or candidate.strategy_id != market.strategy_id
        or candidate.strategy_version != market.strategy_version
    ):
        _append(reasons, TradePlanRefusalReason.CANDIDATE_MISMATCH)
    if not market.source_events or bar.source_event != market.source_events[-1]:
        _append(reasons, TradePlanRefusalReason.SOURCE_EVENT_MISMATCH)
    if value.evidence.authority.provenance.source_object_id != bar.source_event.event_id:
        _append(reasons, TradePlanRefusalReason.SOURCE_EVENT_MISMATCH)
    if value.evidence.authority.authority != SourceAuthority.AUTHORITATIVE:
        _append(reasons, TradePlanRefusalReason.SOURCE_NOT_AUTHORITATIVE)
    if not value.evidence.authority.reconciled:
        _append(reasons, TradePlanRefusalReason.SOURCE_UNRECONCILED)
    if value.evidence.authority.observed_at > value.evaluated_at:
        _append(reasons, TradePlanRefusalReason.EVIDENCE_FUTURE)

    if value.listed_instrument is None:
        _append(reasons, TradePlanRefusalReason.LISTED_INSTRUMENT_MISSING)
    else:
        if value.listed_instrument.economic_instrument != market.economic_instrument:
            _append(reasons, TradePlanRefusalReason.LISTED_INSTRUMENT_MISMATCH)
        if (
            market.market_data_series.series_type == MarketDataSeriesType.CONTINUOUS
            and value.listed_instrument.contract_symbol == market.market_data_series.symbol
        ):
            _append(reasons, TradePlanRefusalReason.CONTINUOUS_SERIES_AS_CONTRACT)

    spec = value.instrument_specification
    if spec is None or value.instrument_authority is None:
        _append(reasons, TradePlanRefusalReason.SPECIFICATION_MISSING)
    else:
        if (
            value.listed_instrument is None
            or spec.product != market.economic_instrument.symbol
            or spec.contract_symbol != value.listed_instrument.contract_symbol
            or spec.exchange != value.listed_instrument.venue
        ):
            _append(reasons, TradePlanRefusalReason.SPECIFICATION_MISMATCH)
        if (
            value.instrument_authority.authority != SourceAuthority.AUTHORITATIVE
            or not value.instrument_authority.reconciled
            or value.instrument_authority.provenance.source_object_id
            != spec.specification_id
        ):
            _append(reasons, TradePlanRefusalReason.SPECIFICATION_NOT_AUTHORITATIVE)

    policy = value.policy
    if policy is None:
        _append(reasons, TradePlanRefusalReason.POLICY_MISSING)
    else:
        if (
            policy.authority.authority != SourceAuthority.AUTHORITATIVE
            or not policy.authority.reconciled
            or policy.authority.provenance.source_object_id != policy.policy_id
        ):
            _append(reasons, TradePlanRefusalReason.POLICY_NOT_AUTHORITATIVE)
        age = Decimal(str((value.evaluated_at - bar.source_event.occurred_at).total_seconds()))
        if age < 0:
            _append(reasons, TradePlanRefusalReason.EVIDENCE_FUTURE)
        elif age > policy.maximum_evidence_age_seconds:
            _append(reasons, TradePlanRefusalReason.EVIDENCE_STALE)

    expires_at = min(value.evidence.entry_bar_closes[-1], value.evidence.session_ends_at)
    if (
        expires_at <= bar.source_event.occurred_at
        or (policy is not None and len(value.evidence.entry_bar_closes)
            != policy.maximum_entry_bars)
        or value.evidence.entry_bar_closes[0] <= bar.source_event.occurred_at
    ):
        _append(reasons, TradePlanRefusalReason.EXPIRY_INVALID)
    if reasons:
        return _refusal(value, reasons)

    assert candidate is not None
    assert value.listed_instrument is not None
    assert spec is not None
    assert value.instrument_authority is not None
    assert policy is not None
    if any(
        candidate_price % spec.tick_size != 0
        for candidate_price in (bar.open, bar.high, bar.low, bar.close)
    ):
        return _refusal(value, [TradePlanRefusalReason.GEOMETRY_INVALID])
    try:
        geometry = _geometry(value)
    except (ArithmeticError, ValueError):
        return _refusal(value, [TradePlanRefusalReason.GEOMETRY_INVALID])
    tick = spec.tick_size
    if value.strategy.direction == StrategyDirection.LONG:
        valid = geometry.target > geometry.entry > geometry.invalidation > geometry.stop
        distance = geometry.entry - geometry.stop
    else:
        valid = geometry.target < geometry.entry < geometry.invalidation < geometry.stop
        distance = geometry.stop - geometry.entry
    if distance < tick:
        return _refusal(value, [TradePlanRefusalReason.RISK_DISTANCE_TOO_SMALL])
    if not valid:
        return _refusal(value, [TradePlanRefusalReason.ROUNDING_COLLAPSE])

    identity_material = {
        "candidate": candidate,
        "source_event": bar.source_event,
        "market_input": market,
        "candidate_ohlc": bar,
        "listed_instrument": value.listed_instrument,
        "instrument_specification": spec,
        "instrument_authority": value.instrument_authority,
        "policy": policy,
        "geometry": geometry,
        "expires_at": expires_at,
    }
    plan_id = sha256_identity(identity_material)
    proposal_authority = AuthorityMetadata(
        authority=SourceAuthority.AUTHORITATIVE,
        provenance=SourceProvenance(
            source_id="atlas.trade_plan",
            source_version=policy.geometry_rule_version,
            source_object_id=plan_id,
            source_sequence=bar.source_event.event_id,
        ),
        observed_at=bar.source_event.occurred_at,
        received_at=bar.source_event.received_at,
        reconciled=True,
    )
    proposal = ProposedTrade(
        proposal_id=plan_id,
        candidate=candidate,
        economic_instrument=market.economic_instrument,
        analysis_series=market.market_data_series,
        listed_instrument=value.listed_instrument,
        direction=value.strategy.direction,
        entry_type="analysis_trigger",
        entry=_price(geometry.entry, tick),
        stop=_price(geometry.stop, tick),
        target=_price(geometry.target, tick),
        invalidation=_price(geometry.invalidation, tick),
        quantity_resolution=QuantityResolution.UNRESOLVED,
        requested_quantity=None,
        created_at=value.evaluated_at,
        evaluated_at=value.evaluated_at,
        rule_id=policy.geometry_rule_id,
        rule_version=policy.geometry_rule_version,
        authority=proposal_authority,
    )
    return TradePlanResult(
        status=TradePlanStatus.GENERATED,
        success=TradePlanSuccess(plan_id, proposal, value.evidence, expires_at),
        refusal=None,
    )
