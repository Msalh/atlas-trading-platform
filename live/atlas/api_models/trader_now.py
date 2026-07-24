"""Allowlisted, immutable TraderNow API response projection."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import Any

from atlas.core.primitives import Price
from atlas.trader_now.models import (
    Availability,
    ContextAvailability,
    ContextProjection,
    InterpretationAvailability,
    InterpretationProjection,
    MarketContext,
    MarketInputWindow,
    MarketSourceAvailability,
    RawSourceTrust,
    RiskProjection,
    RuleAvailability,
    RuleProjection,
    SetupAvailability,
    SetupInsufficientData,
    SetupProjection,
    StrategyAvailability,
    StrategyDecision,
    StrategyProjection,
    TraderNow,
)
from atlas.trader_now.models import InsufficientData as RuleInsufficientData

TRADER_NOW_RESPONSE_SCHEMA_VERSION = "trader_now_response.v2"


@dataclass(frozen=True)
class AvailabilityResponse:
    status: str
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class IdentityResponse:
    product: str
    symbol: str
    timeframe: str
    strategy_id: str
    strategy_version: str


@dataclass(frozen=True)
class EconomicInstrumentResponse:
    symbol: str


@dataclass(frozen=True)
class MarketDataSeriesResponse:
    provider: str
    symbol: str
    series_type: str
    resolved_at: str
    resolution_version: str


@dataclass(frozen=True)
class ListedInstrumentResponse:
    venue: str
    contract_symbol: str
    expiry: str


@dataclass(frozen=True)
class PriceResponse:
    value: float
    tick_size: float


@dataclass(frozen=True)
class MarketBarResponse:
    occurred_at: str
    received_at: str
    schema_version: str
    symbol: str
    timeframe: str
    open: PriceResponse
    high: PriceResponse
    low: PriceResponse
    close: PriceResponse
    volume: float
    volume_ratio: float | None
    atr: float | None
    session_name: str | None
    is_rth: bool | None


@dataclass(frozen=True)
class MarketResponse:
    availability: AvailabilityResponse
    history_availability: AvailabilityResponse
    economic_instrument: EconomicInstrumentResponse | None
    market_data_series: MarketDataSeriesResponse | None
    listed_instrument: ListedInstrumentResponse | None
    observed_at: str | None
    latest_closed_at: str | None
    bar_count: int
    source_schema_versions: tuple[str, ...]
    latest_bar: MarketBarResponse | None


@dataclass(frozen=True)
class FreshnessResponse:
    status: str
    policy_version: str
    evaluated_at: str
    expected_close_at: str | None
    latest_closed_at: str | None
    lateness_seconds: float | None
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class SourceTrustResponse:
    freshness: FreshnessResponse
    availability: str
    structural_validity: str
    overall: str
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class FactResponse:
    fact_id: str
    status: str
    definition_version: str
    value: bool | str | None
    reason: str | None


@dataclass(frozen=True)
class RuleResponse:
    availability: AvailabilityResponse
    schema_version: str | None
    symbol: str | None
    timeframe: str | None
    occurred_at: str | None
    facts: tuple[FactResponse, ...]


@dataclass(frozen=True)
class SetupOutcomeResponse:
    setup_id: str
    status: str
    definition_version: str
    detected: bool | None
    severity: str | None
    reason: str | None
    supporting_fact_ids: tuple[str, ...]


@dataclass(frozen=True)
class SetupResponse:
    availability: AvailabilityResponse
    schema_version: str | None
    symbol: str | None
    timeframe: str | None
    occurred_at: str | None
    setups: tuple[SetupOutcomeResponse, ...]


@dataclass(frozen=True)
class SessionResponse:
    phase: str
    session_open_at: str | None
    session_close_at: str | None
    minutes_since_session_open: int | None
    minutes_until_session_close: int | None
    upstream_session_name: str | None
    upstream_is_rth: bool | None
    drift_status: str


@dataclass(frozen=True)
class VolatilityResponse:
    regime: str
    atr_percentile_rank: float | None
    lookback_bars_used: int


@dataclass(frozen=True)
class ContextDataResponse:
    symbol: str
    timeframe: str
    occurred_at: str
    session: SessionResponse
    volatility: VolatilityResponse
    quality: str
    classifier_version: str
    calendar_version: str
    context_fingerprint: str


@dataclass(frozen=True)
class ContextResponse:
    availability: AvailabilityResponse
    data: ContextDataResponse | None


@dataclass(frozen=True)
class InterpretationItemResponse:
    occurred_at: str
    setup_id: str
    detected: bool
    direction: str
    source: str
    source_fact_ids: tuple[str, ...]
    reason_codes: tuple[str, ...]
    interpretation_version: str
    interpretation_fingerprint: str


@dataclass(frozen=True)
class InterpretationResponse:
    availability: AvailabilityResponse
    interpretations: tuple[InterpretationItemResponse, ...]


@dataclass(frozen=True)
class StrategyDecisionResponse:
    occurred_at: str
    strategy_id: str
    strategy_version: str
    disposition: str
    direction: str
    setup_ids: tuple[str, ...]
    reason_codes: tuple[str, ...]
    context_fingerprint: str
    invalidation: PriceResponse | None
    stop: PriceResponse | None
    target: PriceResponse | None
    confidence: float | None


@dataclass(frozen=True)
class StrategyResponse:
    availability: AvailabilityResponse
    decisions: tuple[StrategyDecisionResponse, ...]


@dataclass(frozen=True)
class RiskResponse:
    schema_version: str
    assessment_id: str
    policy_id: str | None
    policy_version: str | None
    assessed_at: str
    candidate_at: str
    status: str
    primary_reason: str | None
    contributing_reasons: tuple[str, ...]
    sizing_mode: str | None
    requested_quantity: int | None
    maximum_approved_quantity: int | None
    approved_quantity: int | None
    risk_ticks: int | None
    risk_dollars_per_contract: str | None
    approved_total_candidate_risk: str | None
    remaining_daily_risk_capacity: str | None
    remaining_drawdown_capacity: str | None
    exposure_before: int | None
    exposure_after: int | None
    account_freshness: str
    position_freshness: str
    candidate_freshness: str
    reconciliation_status: str | None
    has_delayed_data: bool


@dataclass(frozen=True)
class DecisionResponse:
    availability: str
    state: None


@dataclass(frozen=True)
class TrustResponse:
    status: str
    policy_version: str
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class TraderNowResponse:
    schema_version: str
    domain_schema_version: str
    snapshot_id: str | None
    evaluated_at: str | None
    input_snapshot_at: str | None
    identity: IdentityResponse
    trust: TrustResponse
    availability: Mapping[str, AvailabilityResponse]
    market: MarketResponse
    source_trust: SourceTrustResponse | None
    rules: RuleResponse
    setups: SetupResponse
    context: ContextResponse
    interpretations: InterpretationResponse
    strategy: StrategyResponse
    risk: RiskResponse | None
    decision: DecisionResponse


def _enum(value: Enum | None) -> str | None:
    return None if value is None else str(value.value)


def _datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("public response timestamps must be timezone-aware")
    utc = value.astimezone(timezone.utc)
    return utc.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _decimal(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def _availability(
    value: (
        Availability
        | MarketSourceAvailability
        | RuleAvailability
        | SetupAvailability
        | ContextAvailability
        | InterpretationAvailability
        | StrategyAvailability
    ),
) -> AvailabilityResponse:
    return AvailabilityResponse(
        status=str(value.status.value),
        reason_codes=tuple(
            str(reason.value) if isinstance(reason, Enum) else str(reason)
            for reason in value.reason_codes
        ),
    )


def _price(value: Price | None) -> PriceResponse | None:
    if value is None:
        return None
    return PriceResponse(value=value.value, tick_size=value.tick_size)


def _required_price(value: Price) -> PriceResponse:
    return PriceResponse(value=value.value, tick_size=value.tick_size)


def _market(
    value: MarketInputWindow | None, fallback: AvailabilityResponse
) -> MarketResponse:
    if value is None:
        return MarketResponse(
            fallback, fallback, None, None, None, None, None, 0, (), None
        )
    identity = value.identity
    latest = value.states[-1] if value.states else None
    economic_instrument = None
    market_data_series = None
    listed_instrument = None
    if identity is not None:
        economic_instrument = EconomicInstrumentResponse(
            symbol=identity.economic_instrument.symbol
        )
        series = identity.market_data_series
        market_data_series = MarketDataSeriesResponse(
            provider=series.provider.value,
            symbol=series.symbol,
            series_type=series.series_type.value,
            resolved_at=_datetime(series.resolved_at) or "",
            resolution_version=series.resolution_version,
        )
        if identity.listed_instrument is not None:
            listed = identity.listed_instrument
            listed_instrument = ListedInstrumentResponse(
                venue=listed.venue,
                contract_symbol=listed.contract_symbol,
                expiry=listed.expiry,
            )
    latest_bar = None
    if latest is not None:
        latest_bar = MarketBarResponse(
            occurred_at=_datetime(latest.envelope.occurred_at) or "",
            received_at=_datetime(latest.envelope.received_at) or "",
            schema_version=latest.schema_version,
            symbol=latest.symbol.ticker,
            timeframe=latest.timeframe.value,
            open=_required_price(latest.open),
            high=_required_price(latest.high),
            low=_required_price(latest.low),
            close=_required_price(latest.close),
            volume=latest.volume,
            volume_ratio=latest.volume_ratio,
            atr=latest.atr,
            session_name=_enum(latest.session_name),
            is_rth=latest.is_rth,
        )
    return MarketResponse(
        availability=_availability(value.availability),
        history_availability=_availability(value.history_availability),
        economic_instrument=economic_instrument,
        market_data_series=market_data_series,
        listed_instrument=listed_instrument,
        observed_at=_datetime(identity.observed_at) if identity else None,
        latest_closed_at=_datetime(identity.latest_closed_at) if identity else None,
        bar_count=identity.bar_count if identity else 0,
        source_schema_versions=identity.source_schema_versions if identity else (),
        latest_bar=latest_bar,
    )


def _source_trust(value: RawSourceTrust | None) -> SourceTrustResponse | None:
    if value is None:
        return None
    freshness = value.freshness
    return SourceTrustResponse(
        freshness=FreshnessResponse(
            status=freshness.status.value,
            policy_version=freshness.policy_version,
            evaluated_at=_datetime(freshness.evaluated_at) or "",
            expected_close_at=_datetime(freshness.expected_close_at),
            latest_closed_at=_datetime(freshness.latest_closed_at),
            lateness_seconds=freshness.lateness_seconds,
            reason_codes=tuple(reason.value for reason in freshness.reason_codes),
        ),
        availability=value.availability.value,
        structural_validity=value.structural_validity.value,
        overall=value.overall.value,
        reason_codes=value.reason_codes,
    )


def _rules(
    value: RuleProjection | None, fallback: AvailabilityResponse
) -> RuleResponse:
    if value is None:
        return RuleResponse(fallback, None, None, None, None, ())
    output = value.output
    if output is None:
        return RuleResponse(
            _availability(value.availability), None, None, None, None, ()
        )
    facts = []
    for fact_id, outcome in output.facts.items():
        if isinstance(outcome, RuleInsufficientData):
            facts.append(
                FactResponse(
                    fact_id,
                    "insufficient_data",
                    outcome.definition_version,
                    None,
                    outcome.reason,
                )
            )
        else:
            facts.append(
                FactResponse(
                    fact_id, "computed", outcome.definition_version, outcome.value, None
                )
            )
    return RuleResponse(
        _availability(value.availability),
        output.schema_version,
        output.symbol,
        output.timeframe,
        output.occurred_at,
        tuple(facts),
    )


def _setups(
    value: SetupProjection | None, fallback: AvailabilityResponse
) -> SetupResponse:
    if value is None:
        return SetupResponse(fallback, None, None, None, None, ())
    output = value.output
    if output is None:
        return SetupResponse(
            _availability(value.availability), None, None, None, None, ()
        )
    setups = []
    for outcome in output.setups:
        if isinstance(outcome, SetupInsufficientData):
            setups.append(
                SetupOutcomeResponse(
                    outcome.setup_name,
                    "insufficient_data",
                    outcome.definition_version,
                    None,
                    None,
                    outcome.reason,
                    (),
                )
            )
        else:
            setups.append(
                SetupOutcomeResponse(
                    setup_id=outcome.setup_name,
                    status="computed",
                    definition_version=outcome.definition_version,
                    detected=outcome.detected,
                    severity=_enum(outcome.severity),
                    reason=None,
                    supporting_fact_ids=tuple(
                        fact.fact_name for fact in outcome.evidence.supporting_facts
                    ),
                )
            )
    return SetupResponse(
        _availability(value.availability),
        output.schema_version,
        output.symbol,
        output.timeframe,
        output.occurred_at,
        tuple(setups),
    )


def _context_data(value: MarketContext) -> ContextDataResponse:
    progress = value.session.progress
    return ContextDataResponse(
        symbol=value.symbol.ticker,
        timeframe=value.timeframe.value,
        occurred_at=_datetime(value.occurred_at) or "",
        session=SessionResponse(
            phase=value.session.phase.value,
            session_open_at=_datetime(progress.session_open_at),
            session_close_at=_datetime(progress.session_close_at),
            minutes_since_session_open=progress.minutes_since_session_open,
            minutes_until_session_close=progress.minutes_until_session_close,
            upstream_session_name=value.session.upstream_session_name,
            upstream_is_rth=value.session.upstream_is_rth,
            drift_status=value.session.drift_status.value,
        ),
        volatility=VolatilityResponse(
            regime=value.volatility.regime.value,
            atr_percentile_rank=value.volatility.atr_percentile_rank,
            lookback_bars_used=value.volatility.lookback_bars_used,
        ),
        quality=value.quality.value,
        classifier_version=value.classifier_version,
        calendar_version=value.calendar_version,
        context_fingerprint=value.context_fingerprint,
    )


def _context(
    value: ContextProjection | None, fallback: AvailabilityResponse
) -> ContextResponse:
    if value is None:
        return ContextResponse(fallback, None)
    return ContextResponse(
        _availability(value.availability),
        _context_data(value.output) if value.output is not None else None,
    )


def _interpretations(
    value: InterpretationProjection | None,
    fallback: AvailabilityResponse,
) -> InterpretationResponse:
    if value is None:
        return InterpretationResponse(fallback, ())
    return InterpretationResponse(
        _availability(value.availability),
        tuple(
            InterpretationItemResponse(
                occurred_at=_datetime(item.occurred_at) or "",
                setup_id=item.setup_id,
                detected=item.detected,
                direction=item.direction.value,
                source=item.source.value,
                source_fact_ids=item.source_fact_ids,
                reason_codes=item.reason_codes,
                interpretation_version=item.interpretation_version,
                interpretation_fingerprint=item.interpretation_fingerprint,
            )
            for item in value.output
        ),
    )


def _strategy_decision(value: StrategyDecision) -> StrategyDecisionResponse:
    return StrategyDecisionResponse(
        occurred_at=_datetime(value.occurred_at) or "",
        strategy_id=value.strategy_id,
        strategy_version=value.strategy_version,
        disposition=value.disposition.value,
        direction=value.direction.value,
        setup_ids=value.setup_ids,
        reason_codes=value.reason_codes,
        context_fingerprint=value.context_fingerprint,
        invalidation=_price(value.invalidation),
        stop=_price(value.stop),
        target=_price(value.target),
        confidence=value.confidence,
    )


def _strategy(
    value: StrategyProjection | None,
    fallback: AvailabilityResponse,
) -> StrategyResponse:
    if value is None:
        return StrategyResponse(fallback, ())
    return StrategyResponse(
        _availability(value.availability),
        tuple(_strategy_decision(decision) for decision in value.output),
    )


def _risk(value: RiskProjection | None) -> RiskResponse | None:
    if value is None:
        return None
    return RiskResponse(
        schema_version=value.schema_version,
        assessment_id=value.assessment_id,
        policy_id=value.policy_id,
        policy_version=value.policy_version,
        assessed_at=_datetime(value.assessed_at) or "",
        candidate_at=_datetime(value.candidate_at) or "",
        status=value.status.value,
        primary_reason=_enum(value.primary_reason),
        contributing_reasons=tuple(
            reason.value for reason in value.contributing_reasons
        ),
        sizing_mode=_enum(value.sizing_mode),
        requested_quantity=value.requested_quantity,
        maximum_approved_quantity=value.maximum_approved_quantity,
        approved_quantity=value.approved_quantity,
        risk_ticks=value.risk_ticks,
        risk_dollars_per_contract=_decimal(value.risk_dollars_per_contract),
        approved_total_candidate_risk=_decimal(value.approved_total_candidate_risk),
        remaining_daily_risk_capacity=_decimal(value.remaining_daily_risk_capacity),
        remaining_drawdown_capacity=_decimal(value.remaining_drawdown_capacity),
        exposure_before=value.exposure_before,
        exposure_after=value.exposure_after,
        account_freshness=value.account_freshness.value,
        position_freshness=value.position_freshness.value,
        candidate_freshness=value.candidate_freshness.value,
        reconciliation_status=_enum(value.reconciliation_status),
        has_delayed_data=value.has_delayed_data,
    )


def project_trader_now_response(value: TraderNow) -> TraderNowResponse:
    """Project the canonical domain read model into the public allowlist."""
    availability = MappingProxyType(
        {
            section: _availability(section_availability)
            for section, section_availability in sorted(value.availability.items())
        }
    )
    unavailable = AvailabilityResponse("unavailable", ("projection_unavailable",))

    def section(name: str) -> AvailabilityResponse:
        return availability.get(name, unavailable)

    market_identity = value.market.identity if value.market is not None else None
    source_trust = _source_trust(value.source_trust)
    return TraderNowResponse(
        schema_version=TRADER_NOW_RESPONSE_SCHEMA_VERSION,
        domain_schema_version=value.schema_version,
        snapshot_id=value.snapshot.value if value.snapshot is not None else None,
        evaluated_at=source_trust.freshness.evaluated_at if source_trust else None,
        input_snapshot_at=(
            _datetime(market_identity.latest_closed_at) if market_identity else None
        ),
        identity=IdentityResponse(
            product=value.identity.product,
            symbol=value.identity.symbol,
            timeframe=value.identity.timeframe,
            strategy_id=value.identity.strategy_id,
            strategy_version=value.identity.strategy_version,
        ),
        trust=TrustResponse(
            status=value.trust.status.value,
            policy_version=value.trust.policy_version,
            reason_codes=value.trust.reason_codes,
        ),
        availability=availability,
        market=_market(value.market, section("market")),
        source_trust=source_trust,
        rules=_rules(value.rules, section("rules")),
        setups=_setups(value.setups, section("setups")),
        context=_context(value.context, section("context")),
        interpretations=_interpretations(
            value.interpretations, section("interpretations")
        ),
        strategy=_strategy(value.strategy, section("strategy")),
        risk=_risk(value.risk),
        decision=DecisionResponse(value.decision.availability.value, None),
    )


def _to_public(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return {
            name: _to_public(getattr(value, name))
            for name in value.__dataclass_fields__
        }
    if isinstance(value, tuple):
        return [_to_public(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _to_public(nested) for key, nested in value.items()}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return _datetime(value)
    if isinstance(value, Decimal):
        return _decimal(value)
    return value


def trader_now_response_to_dict(value: TraderNowResponse) -> dict[str, Any]:
    """Return a new JSON-safe object containing DTO fields only."""
    result = _to_public(value)
    if not isinstance(result, dict):
        raise TypeError("TraderNowResponse serialization must produce an object")
    return result


def trader_now_response_to_json(value: TraderNowResponse) -> str:
    """Return canonical compact JSON with lexicographically sorted keys."""
    return json.dumps(
        trader_now_response_to_dict(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
