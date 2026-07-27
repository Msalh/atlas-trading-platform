"""Pure fail-closed validation and canonical market-evidence adaptation."""

from __future__ import annotations

from datetime import datetime, timedelta
from itertools import pairwise
from typing import TypeVar

from atlas.risk_assessment.models import InstrumentSpecification
from atlas.trade_plan.models import TradePlanPolicy
from atlas.trade_risk_authority.models import SourceAuthority
from atlas.trader_now.models import (
    AvailabilityStatus,
    ListedInstrument,
    MarketDataSeriesType,
    MarketInputWindow,
)

from .models import (
    AuthorityKind,
    AuthorityReason,
    AuthorityRecord,
    AuthorityResolution,
    AuthoritySource,
    AuthorityStatus,
    CanonicalMarketEvidence,
    CanonicalMarketEvidenceResolution,
    EffectiveInterval,
    ExchangeSessionAuthorityRequest,
    InstrumentSpecificationAuthorityRequest,
    ListedContractAuthorityRequest,
    PlanExpiryInputs,
    TradePlanPolicyAuthorityRequest,
    authority_resolution,
)

T = TypeVar("T")

_TIMEFRAME_CADENCE: dict[str, timedelta] = {
    "1m": timedelta(minutes=1),
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "30m": timedelta(minutes=30),
    "1h": timedelta(hours=1),
}


def resolve_authority_records(
    *,
    kind: AuthorityKind,
    evaluated_at: datetime,
    records: tuple[AuthorityRecord[T], ...],
    resolution_source: AuthoritySource,
) -> AuthorityResolution[T]:
    """Select one effective record or return one explicit closed outcome."""

    unknown_interval = EffectiveInterval(None, None)
    if not records:
        return authority_resolution(
            kind=kind,
            status=AuthorityStatus.UNAVAILABLE,
            evaluated_at=evaluated_at,
            effective_interval=unknown_interval,
            source=resolution_source,
            reasons=(AuthorityReason.MISSING,),
        )
    if any(
        record.source.observed_at > evaluated_at
        or record.source.retrieved_at > evaluated_at
        for record in records
    ):
        return authority_resolution(
            kind=kind,
            status=AuthorityStatus.UNAVAILABLE,
            evaluated_at=evaluated_at,
            effective_interval=unknown_interval,
            source=resolution_source,
            reasons=(AuthorityReason.FUTURE_DATED,),
        )
    if any(not record.source.reconciled for record in records):
        return authority_resolution(
            kind=kind,
            status=AuthorityStatus.UNAVAILABLE,
            evaluated_at=evaluated_at,
            effective_interval=unknown_interval,
            source=resolution_source,
            reasons=(AuthorityReason.UNRECONCILED,),
        )
    effective = tuple(
        record for record in records if record.effective_interval.contains(evaluated_at)
    )
    if len(effective) > 1:
        return authority_resolution(
            kind=kind,
            status=AuthorityStatus.CONFLICTING,
            evaluated_at=evaluated_at,
            effective_interval=unknown_interval,
            source=resolution_source,
            reasons=(AuthorityReason.OVERLAPPING, AuthorityReason.CONFLICTING),
        )
    if not effective:
        latest = max(
            records,
            key=lambda record: (
                record.effective_interval.ends_at
                or record.effective_interval.starts_at
                or datetime.min.replace(tzinfo=evaluated_at.tzinfo)
            ),
        )
        return authority_resolution(
            kind=kind,
            status=AuthorityStatus.STALE,
            evaluated_at=evaluated_at,
            effective_interval=latest.effective_interval,
            source=latest.source,
            reasons=(AuthorityReason.STALE,),
        )
    selected = effective[0]
    return authority_resolution(
        kind=kind,
        status=AuthorityStatus.AVAILABLE,
        evaluated_at=evaluated_at,
        effective_interval=selected.effective_interval,
        source=selected.source,
        value=selected.value,
    )


def _closed(
    resolution: AuthorityResolution[T],
    *reasons: AuthorityReason,
    status: AuthorityStatus = AuthorityStatus.UNAVAILABLE,
) -> AuthorityResolution[T]:
    return authority_resolution(
        kind=resolution.kind,
        status=status,
        evaluated_at=resolution.evaluated_at,
        effective_interval=resolution.effective_interval,
        source=resolution.source,
        reasons=tuple(dict.fromkeys(reasons)),
    )


def validate_listed_contract(
    request: ListedContractAuthorityRequest,
    resolution: AuthorityResolution[ListedInstrument],
) -> AuthorityResolution[ListedInstrument]:
    if resolution.kind != AuthorityKind.LISTED_CONTRACT:
        raise ValueError("listed-contract resolution kind mismatch")
    if resolution.evaluated_at != request.evaluated_at:
        raise ValueError("listed-contract evaluation time mismatch")
    if resolution.status != AuthorityStatus.AVAILABLE:
        return resolution
    assert resolution.value is not None
    listed = resolution.value
    if (
        listed.economic_instrument != request.economic_instrument
        or request.analysis_series.economic_instrument != request.economic_instrument
    ):
        return _closed(
            resolution,
            AuthorityReason.IDENTITY_MISMATCH,
            status=AuthorityStatus.CONFLICTING,
        )
    if (
        request.analysis_series.series_type == MarketDataSeriesType.CONTINUOUS
        and listed.contract_symbol == request.analysis_series.symbol
    ):
        return _closed(
            resolution,
            AuthorityReason.CONTINUOUS_SERIES_AS_LISTED,
            status=AuthorityStatus.CONFLICTING,
        )
    return resolution


def validate_instrument_specification(
    request: InstrumentSpecificationAuthorityRequest,
    resolution: AuthorityResolution[InstrumentSpecification],
) -> AuthorityResolution[InstrumentSpecification]:
    if resolution.kind != AuthorityKind.INSTRUMENT_SPECIFICATION:
        raise ValueError("instrument-specification resolution kind mismatch")
    if resolution.evaluated_at != request.evaluated_at:
        raise ValueError("instrument-specification evaluation time mismatch")
    if resolution.status != AuthorityStatus.AVAILABLE:
        return resolution
    assert resolution.value is not None
    spec = resolution.value
    listed = request.listed_instrument
    if (
        spec.product != listed.economic_instrument.symbol
        or spec.contract_symbol != listed.contract_symbol
        or spec.exchange != listed.venue
    ):
        return _closed(
            resolution,
            AuthorityReason.IDENTITY_MISMATCH,
            status=AuthorityStatus.CONFLICTING,
        )
    return resolution


def validate_exchange_session(
    request: ExchangeSessionAuthorityRequest,
    resolution: AuthorityResolution[PlanExpiryInputs],
) -> AuthorityResolution[PlanExpiryInputs]:
    if resolution.kind != AuthorityKind.EXCHANGE_SESSION:
        raise ValueError("exchange-session resolution kind mismatch")
    if resolution.evaluated_at != request.evaluated_at:
        raise ValueError("exchange-session evaluation time mismatch")
    if resolution.status != AuthorityStatus.AVAILABLE:
        return resolution
    assert resolution.value is not None
    value = resolution.value
    if (
        value.listed_instrument != request.listed_instrument
        or value.timeframe != request.timeframe
        or len(value.eligible_entry_bar_closes) != request.maximum_entry_bars
        or not value.session_opens_at
        < request.candidate_closed_at
        <= value.session_ends_at
        or any(
            period.contains(request.candidate_closed_at)
            for period in value.maintenance_periods
        )
        or value.eligible_entry_bar_closes[0] <= request.candidate_closed_at
    ):
        return _closed(
            resolution,
            AuthorityReason.EXCHANGE_SESSION_MISMATCH,
            status=AuthorityStatus.CONFLICTING,
        )
    return resolution


def validate_trade_plan_policy(
    request: TradePlanPolicyAuthorityRequest,
    resolution: AuthorityResolution[TradePlanPolicy],
) -> AuthorityResolution[TradePlanPolicy]:
    if resolution.kind != AuthorityKind.TRADE_PLAN_POLICY:
        raise ValueError("trade-plan-policy resolution kind mismatch")
    if resolution.evaluated_at != request.evaluated_at:
        raise ValueError("trade-plan-policy evaluation time mismatch")
    if resolution.status != AuthorityStatus.AVAILABLE:
        return resolution
    assert resolution.value is not None
    policy = resolution.value
    if (
        policy.authority.authority != SourceAuthority.AUTHORITATIVE
        or not policy.authority.reconciled
        or policy.authority.provenance.source_object_id != policy.policy_id
    ):
        return _closed(resolution, AuthorityReason.UNRECONCILED)
    return resolution


def adapt_canonical_market_input(
    market_input: MarketInputWindow,
    *,
    source: AuthoritySource,
) -> CanonicalMarketEvidenceResolution:
    evaluated_at = market_input.availability.observed_at
    interval = EffectiveInterval(
        starts_at=(
            market_input.identity.latest_closed_at
            if market_input.identity is not None
            else None
        ),
        ends_at=None,
    )
    if source.observed_at > evaluated_at or source.retrieved_at > evaluated_at:
        return authority_resolution(
            kind=AuthorityKind.CANONICAL_MARKET_EVIDENCE,
            status=AuthorityStatus.UNAVAILABLE,
            evaluated_at=evaluated_at,
            effective_interval=interval,
            source=source,
            reasons=(AuthorityReason.FUTURE_DATED,),
        )
    if not source.reconciled:
        return authority_resolution(
            kind=AuthorityKind.CANONICAL_MARKET_EVIDENCE,
            status=AuthorityStatus.UNAVAILABLE,
            evaluated_at=evaluated_at,
            effective_interval=interval,
            source=source,
            reasons=(AuthorityReason.UNRECONCILED,),
        )
    if (
        market_input.availability.status != AvailabilityStatus.AVAILABLE
        or market_input.identity is None
        or not market_input.states
    ):
        return authority_resolution(
            kind=AuthorityKind.CANONICAL_MARKET_EVIDENCE,
            status=AuthorityStatus.UNAVAILABLE,
            evaluated_at=evaluated_at,
            effective_interval=interval,
            source=source,
            reasons=(AuthorityReason.MARKET_UNAVAILABLE,),
        )
    identity = market_input.identity
    cadence = _TIMEFRAME_CADENCE.get(identity.timeframe)
    if (
        identity.bar_count != 288
        or len(identity.source_events) != 288
        or len(market_input.states) != 288
    ):
        return authority_resolution(
            kind=AuthorityKind.CANONICAL_MARKET_EVIDENCE,
            status=AuthorityStatus.UNAVAILABLE,
            evaluated_at=evaluated_at,
            effective_interval=interval,
            source=source,
            reasons=(AuthorityReason.MARKET_HISTORY_NOT_CANONICAL,),
        )
    if cadence is None:
        return authority_resolution(
            kind=AuthorityKind.CANONICAL_MARKET_EVIDENCE,
            status=AuthorityStatus.UNAVAILABLE,
            evaluated_at=evaluated_at,
            effective_interval=interval,
            source=source,
            reasons=(AuthorityReason.MARKET_HISTORY_NOT_CANONICAL,),
        )
    state_events = tuple(state.envelope for state in market_input.states)
    if any(
        identity_event.event_id != state_event.event_id
        or identity_event.occurred_at != state_event.occurred_at
        or identity_event.received_at != state_event.received_at
        for identity_event, state_event in zip(identity.source_events, state_events)
    ):
        return authority_resolution(
            kind=AuthorityKind.CANONICAL_MARKET_EVIDENCE,
            status=AuthorityStatus.CONFLICTING,
            evaluated_at=evaluated_at,
            effective_interval=interval,
            source=source,
            reasons=(AuthorityReason.SOURCE_EVENT_MISMATCH,),
        )
    event_ids = tuple(event.event_id for event in identity.source_events)
    timestamps = tuple(event.occurred_at for event in identity.source_events)
    if (
        len(set(event_ids)) != 288
        or len(set(timestamps)) != 288
        or any(current <= previous for previous, current in pairwise(timestamps))
    ):
        return authority_resolution(
            kind=AuthorityKind.CANONICAL_MARKET_EVIDENCE,
            status=AuthorityStatus.CONFLICTING,
            evaluated_at=evaluated_at,
            effective_interval=interval,
            source=source,
            reasons=(AuthorityReason.SOURCE_EVENT_ORDER_INVALID,),
        )
    if any(current - previous != cadence for previous, current in pairwise(timestamps)):
        return authority_resolution(
            kind=AuthorityKind.CANONICAL_MARKET_EVIDENCE,
            status=AuthorityStatus.CONFLICTING,
            evaluated_at=evaluated_at,
            effective_interval=interval,
            source=source,
            reasons=(AuthorityReason.MARKET_CADENCE_INVALID,),
        )
    if (
        identity.latest_closed_at != timestamps[-1]
        or market_input.states[-1].envelope.occurred_at != timestamps[-1]
    ):
        return authority_resolution(
            kind=AuthorityKind.CANONICAL_MARKET_EVIDENCE,
            status=AuthorityStatus.CONFLICTING,
            evaluated_at=evaluated_at,
            effective_interval=interval,
            source=source,
            reasons=(AuthorityReason.SOURCE_EVENT_MISMATCH,),
        )
    evidence = CanonicalMarketEvidence(
        market_input=identity,
        latest_source_event=identity.source_events[-1],
        source_event_ids=tuple(event.event_id for event in identity.source_events),
        source_event_timestamps=timestamps,
        timeframe=identity.timeframe,
        expected_cadence_seconds=int(cadence.total_seconds()),
    )
    return authority_resolution(
        kind=AuthorityKind.CANONICAL_MARKET_EVIDENCE,
        status=AuthorityStatus.AVAILABLE,
        evaluated_at=evaluated_at,
        effective_interval=interval,
        source=source,
        value=evidence,
    )


def require_sufficient_context_history(
    resolution: CanonicalMarketEvidenceResolution,
    *,
    sufficient: bool,
) -> CanonicalMarketEvidenceResolution:
    """Fail closed when the frozen Context prerequisite is unavailable."""

    if resolution.status != AuthorityStatus.AVAILABLE or sufficient:
        return resolution
    return _closed(resolution, AuthorityReason.CONTEXT_INSUFFICIENT_HISTORY)
