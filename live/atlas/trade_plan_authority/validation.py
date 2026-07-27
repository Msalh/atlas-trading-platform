"""Pure fail-closed validation and canonical market-evidence adaptation."""

from __future__ import annotations

from datetime import datetime
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
    InstrumentSpecificationAuthorityRequest,
    ListedContractAuthorityRequest,
    PlanExpiryInputs,
    TradePlanPolicyAuthorityRequest,
    authority_resolution,
)

T = TypeVar("T")


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
    resolution: AuthorityResolution[PlanExpiryInputs],
    *,
    expected_entry_bar_count: int,
) -> AuthorityResolution[PlanExpiryInputs]:
    if resolution.kind != AuthorityKind.EXCHANGE_SESSION:
        raise ValueError("exchange-session resolution kind mismatch")
    if resolution.status != AuthorityStatus.AVAILABLE:
        return resolution
    assert resolution.value is not None
    if len(resolution.value.eligible_entry_bar_closes) != expected_entry_bar_count:
        return _closed(
            resolution,
            AuthorityReason.IDENTITY_MISMATCH,
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
    timestamps = tuple(event.occurred_at for event in identity.source_events)
    if len(set(timestamps)) != 288 or any(
        current <= previous for previous, current in pairwise(timestamps)
    ):
        return authority_resolution(
            kind=AuthorityKind.CANONICAL_MARKET_EVIDENCE,
            status=AuthorityStatus.CONFLICTING,
            evaluated_at=evaluated_at,
            effective_interval=interval,
            source=source,
            reasons=(AuthorityReason.SOURCE_EVENT_ORDER_INVALID,),
        )
    evidence = CanonicalMarketEvidence(
        market_input=identity,
        latest_source_event=identity.source_events[-1],
        source_event_ids=tuple(event.event_id for event in identity.source_events),
        source_event_timestamps=timestamps,
    )
    return authority_resolution(
        kind=AuthorityKind.CANONICAL_MARKET_EVIDENCE,
        status=AuthorityStatus.AVAILABLE,
        evaluated_at=evaluated_at,
        effective_interval=interval,
        source=source,
        value=evidence,
    )
