import hashlib
import json
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from atlas.core.events import Event
from atlas.core.primitives import Symbol, Timeframe
from atlas.market_engine.models import BarStatus, MarketState
from atlas.risk_assessment.models import InstrumentSpecification, SourceProvenance
from atlas.trade_plan.models import TradePlanPolicy
from atlas.trade_plan_authority import (
    AuthorityKind,
    AuthorityReason,
    AuthorityRecord,
    AuthorityResolution,
    AuthoritySource,
    AuthorityStatus,
    EffectiveInterval,
    ExchangeSessionAuthorityRequest,
    InstrumentSpecificationAuthorityRequest,
    ListedContractAuthorityRequest,
    PlanExpiryInputs,
    TradePlanPolicyAuthorityRequest,
    adapt_canonical_market_input,
    authority_resolution,
    canonical_bytes,
    require_sufficient_context_history,
    resolve_authority_records,
    validate_exchange_session,
    validate_instrument_specification,
    validate_listed_contract,
    validate_trade_plan_policy,
)
from atlas.trade_risk_authority.models import AuthorityMetadata, SourceAuthority
from atlas.trader_now.models import (
    AvailabilityStatus,
    EconomicInstrument,
    ListedInstrument,
    MarketDataProvider,
    MarketDataSeries,
    MarketDataSeriesType,
    MarketInputIdentity,
    MarketInputWindow,
    MarketSourceAvailability,
    SourceEventIdentity,
)

AT = datetime(2026, 7, 27, 5, 40, 30, tzinfo=timezone.utc)
START = datetime(2026, 6, 19, tzinfo=timezone.utc)
END = datetime(2026, 9, 18, tzinfo=timezone.utc)
FIXTURES = (
    Path(__file__).parents[1] / "specs" / "product_p2b_2a" / "v1" / "fixtures.json"
)


def product() -> EconomicInstrument:
    return EconomicInstrument("MNQ")


def series() -> MarketDataSeries:
    return MarketDataSeries(
        economic_instrument=product(),
        provider=MarketDataProvider.TRADINGVIEW,
        symbol="MNQ1!",
        series_type=MarketDataSeriesType.CONTINUOUS,
        resolved_at=AT,
        resolution_version="test-series.v1",
        resolution_owner="test-only",
    )


def source(**changes) -> AuthoritySource:
    return replace(
        AuthoritySource(
            provider_id="test-only-reference-authority",
            provider_version="test-provider.v1",
            source_id="test-only-source-record",
            source_version="test-source.v7",
            observed_at=AT - timedelta(minutes=2),
            retrieved_at=AT - timedelta(minutes=1),
            reconciled=True,
        ),
        **changes,
    )


def interval(**changes) -> EffectiveInterval:
    return replace(EffectiveInterval(START, END), **changes)


def listed(symbol: str = "TEST-MNQU6") -> ListedInstrument:
    return ListedInstrument(product(), "TEST-CME", symbol, "2026-09")


def listed_request() -> ListedContractAuthorityRequest:
    return ListedContractAuthorityRequest(product(), series(), AT)


def listed_resolution(
    *,
    value: ListedInstrument | None = None,
    status: AuthorityStatus = AuthorityStatus.AVAILABLE,
    reasons: tuple[AuthorityReason, ...] = (),
    authority_source: AuthoritySource | None = None,
    effective: EffectiveInterval | None = None,
):
    return authority_resolution(
        kind=AuthorityKind.LISTED_CONTRACT,
        status=status,
        evaluated_at=AT,
        effective_interval=effective or interval(),
        source=authority_source or source(),
        value=listed()
        if value is None and status == AuthorityStatus.AVAILABLE
        else value,
        reasons=reasons,
    )


def provenance(source_id: str, object_id: str) -> SourceProvenance:
    return SourceProvenance(source_id, "test-only.v1", object_id, "1")


def p2a_authority(object_id: str) -> AuthorityMetadata:
    return AuthorityMetadata(
        SourceAuthority.AUTHORITATIVE,
        provenance("test-only-authority", object_id),
        AT - timedelta(minutes=2),
        AT - timedelta(minutes=1),
        True,
    )


def specification(contract_symbol: str = "TEST-MNQU6") -> InstrumentSpecification:
    return InstrumentSpecification(
        specification_id="test-only-mnq-spec",
        product="MNQ",
        contract_symbol=contract_symbol,
        asset_class="future",
        exchange="TEST-CME",
        currency="USD",
        tick_size=Decimal("0.25"),
        tick_value=Decimal("0.50"),
        point_value=Decimal(2),
        contract_multiplier=Decimal(2),
        minimum_quantity=1,
        quantity_increment=1,
        price_precision=2,
        session_calendar_id="test-only-calendar",
        provenance=provenance("test-only-specification", "test-only-mnq-spec"),
    )


def policy() -> TradePlanPolicy:
    return TradePlanPolicy(
        policy_id="test-only-trade-plan-policy",
        policy_version="1",
        geometry_rule_id="candidate-bar-break.v1",
        geometry_rule_version="1",
        reward_multiple=Decimal("1.9"),
        maximum_entry_bars=2,
        maximum_evidence_age_seconds=Decimal(120),
        authority=p2a_authority("test-only-trade-plan-policy"),
    )


def test_available_resolution_is_deterministic_immutable_and_byte_stable():
    first = listed_resolution()
    second = listed_resolution()
    golden = json.loads(FIXTURES.read_text(encoding="utf-8"))["golden_serialization"]
    assert first == second
    assert first.resolution_id == second.resolution_id
    assert first.resolution_id == golden["listed_resolution_id"]
    assert canonical_bytes(first) == canonical_bytes(second)
    assert (
        hashlib.sha256(canonical_bytes(first)).hexdigest()
        == golden["listed_resolution_sha256"]
    )
    with pytest.raises(FrozenInstanceError):
        first.status = AuthorityStatus.STALE  # type: ignore[misc]


def test_resolution_identity_rejects_tampering():
    value = listed_resolution()
    with pytest.raises(ValueError, match="identity mismatch"):
        replace(value, resolution_id="0" * 64)


def test_effective_interval_is_start_inclusive_and_end_exclusive():
    value = interval()
    assert value.contains(START)
    assert value.contains(END - timedelta(microseconds=1))
    assert not value.contains(END)
    with pytest.raises(ValueError, match="effective"):
        authority_resolution(
            kind=AuthorityKind.LISTED_CONTRACT,
            status=AuthorityStatus.AVAILABLE,
            evaluated_at=END,
            effective_interval=value,
            source=source(),
            value=listed(),
        )


@pytest.mark.parametrize(
    ("status", "reasons"),
    (
        (AuthorityStatus.UNAVAILABLE, (AuthorityReason.MISSING,)),
        (AuthorityStatus.STALE, (AuthorityReason.STALE,)),
        (
            AuthorityStatus.CONFLICTING,
            (AuthorityReason.OVERLAPPING, AuthorityReason.CONFLICTING),
        ),
    ),
)
def test_nonavailable_authority_is_explicit_and_carries_no_value(status, reasons):
    value = listed_resolution(status=status, reasons=reasons)
    assert value.status == status
    assert value.value is None
    assert value.reasons == reasons


def test_available_authority_rejects_future_and_unreconciled_sources():
    with pytest.raises(ValueError, match="future-observed"):
        listed_resolution(
            authority_source=source(
                observed_at=AT + timedelta(seconds=1),
                retrieved_at=AT + timedelta(seconds=2),
            )
        )
    with pytest.raises(ValueError, match="reconciled"):
        listed_resolution(authority_source=source(reconciled=False))


def test_future_and_unreconciled_failures_are_closed_without_values():
    future = listed_resolution(
        status=AuthorityStatus.UNAVAILABLE,
        reasons=(AuthorityReason.FUTURE_DATED,),
        authority_source=source(
            observed_at=AT + timedelta(seconds=1),
            retrieved_at=AT + timedelta(seconds=2),
        ),
    )
    unreconciled = listed_resolution(
        status=AuthorityStatus.UNAVAILABLE,
        reasons=(AuthorityReason.UNRECONCILED,),
        authority_source=source(reconciled=False),
    )
    assert future.value is None
    assert unreconciled.value is None


def test_conflicting_provider_values_are_explicit_and_identity_sensitive():
    first = listed_resolution()
    second = listed_resolution(
        authority_source=source(
            provider_id="test-only-secondary-authority",
            source_id="test-only-conflicting-record",
        )
    )
    conflict = listed_resolution(
        status=AuthorityStatus.CONFLICTING,
        reasons=(AuthorityReason.OVERLAPPING, AuthorityReason.CONFLICTING),
    )
    assert first.resolution_id != second.resolution_id
    assert conflict.value is None
    assert conflict.status == AuthorityStatus.CONFLICTING


def test_record_selection_detects_overlaps_instead_of_choosing_a_provider():
    records = (
        AuthorityRecord(listed(), interval(), source()),
        AuthorityRecord(
            listed("TEST-MNQZ6"),
            interval(),
            source(
                provider_id="test-only-secondary-authority",
                source_id="test-only-conflicting-record",
            ),
        ),
    )
    result = resolve_authority_records(
        kind=AuthorityKind.LISTED_CONTRACT,
        evaluated_at=AT,
        records=records,
        resolution_source=source(
            provider_id="test-only-reconciler",
            source_id="test-only-resolution-attempt",
        ),
    )
    assert result.status == AuthorityStatus.CONFLICTING
    assert result.value is None
    assert result.reasons == (
        AuthorityReason.OVERLAPPING,
        AuthorityReason.CONFLICTING,
    )


def test_record_selection_returns_missing_stale_future_and_unreconciled_outcomes():
    resolver = source(
        provider_id="test-only-reconciler",
        source_id="test-only-resolution-attempt",
    )
    missing = resolve_authority_records(
        kind=AuthorityKind.LISTED_CONTRACT,
        evaluated_at=AT,
        records=(),
        resolution_source=resolver,
    )
    stale = resolve_authority_records(
        kind=AuthorityKind.LISTED_CONTRACT,
        evaluated_at=AT,
        records=(
            AuthorityRecord(
                listed(),
                EffectiveInterval(START, AT),
                source(),
            ),
        ),
        resolution_source=resolver,
    )
    future = resolve_authority_records(
        kind=AuthorityKind.LISTED_CONTRACT,
        evaluated_at=AT,
        records=(
            AuthorityRecord(
                listed(),
                interval(),
                source(
                    observed_at=AT + timedelta(seconds=1),
                    retrieved_at=AT + timedelta(seconds=2),
                ),
            ),
        ),
        resolution_source=resolver,
    )
    unreconciled = resolve_authority_records(
        kind=AuthorityKind.LISTED_CONTRACT,
        evaluated_at=AT,
        records=(
            AuthorityRecord(
                listed(),
                interval(),
                source(reconciled=False),
            ),
        ),
        resolution_source=resolver,
    )
    assert missing.reasons == (AuthorityReason.MISSING,)
    assert stale.status == AuthorityStatus.STALE
    assert future.reasons == (AuthorityReason.FUTURE_DATED,)
    assert unreconciled.reasons == (AuthorityReason.UNRECONCILED,)
    assert all(item.value is None for item in (missing, stale, future, unreconciled))


def test_expired_record_is_represented_as_stale_without_a_value():
    stale = listed_resolution(
        status=AuthorityStatus.STALE,
        reasons=(AuthorityReason.STALE,),
        effective=EffectiveInterval(START, AT),
    )
    assert not stale.effective_interval.contains(AT)
    assert stale.value is None


def test_listed_contract_preserves_product_series_and_contract_boundaries():
    result = validate_listed_contract(listed_request(), listed_resolution())
    assert result.status == AuthorityStatus.AVAILABLE
    assert result.value is not None
    assert result.value.economic_instrument.symbol == "MNQ"
    assert listed_request().analysis_series.symbol == "MNQ1!"
    assert result.value.contract_symbol == "TEST-MNQU6"


def test_continuous_analysis_series_is_never_a_listed_contract():
    result = validate_listed_contract(
        listed_request(), listed_resolution(value=listed("MNQ1!"))
    )
    assert result.status == AuthorityStatus.CONFLICTING
    assert result.value is None
    assert result.reasons == (AuthorityReason.CONTINUOUS_SERIES_AS_LISTED,)


def test_instrument_specification_mismatch_fails_closed():
    request = InstrumentSpecificationAuthorityRequest(listed(), AT)
    resolution = authority_resolution(
        kind=AuthorityKind.INSTRUMENT_SPECIFICATION,
        status=AuthorityStatus.AVAILABLE,
        evaluated_at=AT,
        effective_interval=interval(),
        source=source(),
        value=specification("TEST-MNQZ6"),
    )
    result = validate_instrument_specification(request, resolution)
    assert result.status == AuthorityStatus.CONFLICTING
    assert result.value is None
    assert result.reasons == (AuthorityReason.IDENTITY_MISMATCH,)


def expiry_inputs() -> PlanExpiryInputs:
    return PlanExpiryInputs(
        listed_instrument=listed(),
        timeframe="5m",
        calendar_id="test-only-cme-calendar",
        calendar_version="test-calendar.v1",
        session_id="test-session-2026-07-27",
        session_opens_at=datetime(2026, 7, 26, 22, tzinfo=timezone.utc),
        session_ends_at=datetime(2026, 7, 27, 21, tzinfo=timezone.utc),
        maintenance_periods=(),
        eligible_entry_bar_closes=(
            datetime(2026, 7, 27, 5, 45, tzinfo=timezone.utc),
            datetime(2026, 7, 27, 5, 50, tzinfo=timezone.utc),
        ),
    )


def test_exchange_session_contract_and_entry_count_are_exact():
    request = ExchangeSessionAuthorityRequest(
        listed(), datetime(2026, 7, 27, 5, 40, tzinfo=timezone.utc), "5m", 2, AT
    )
    resolution = authority_resolution(
        kind=AuthorityKind.EXCHANGE_SESSION,
        status=AuthorityStatus.AVAILABLE,
        evaluated_at=request.evaluated_at,
        effective_interval=EffectiveInterval(
            request.candidate_closed_at, expiry_inputs().session_ends_at
        ),
        source=source(),
        value=expiry_inputs(),
    )
    assert (
        validate_exchange_session(request, resolution).status
        == AuthorityStatus.AVAILABLE
    )
    refused = validate_exchange_session(
        replace(request, maximum_entry_bars=3), resolution
    )
    assert refused.status == AuthorityStatus.CONFLICTING
    assert refused.value is None


def test_exchange_session_is_bound_to_request_identity_and_maintenance():
    request = ExchangeSessionAuthorityRequest(
        listed(), datetime(2026, 7, 27, 5, 40, tzinfo=timezone.utc), "5m", 2, AT
    )
    maintenance = EffectiveInterval(
        datetime(2026, 7, 27, 5, 35, tzinfo=timezone.utc),
        datetime(2026, 7, 27, 5, 41, tzinfo=timezone.utc),
    )
    inputs = replace(
        expiry_inputs(),
        maintenance_periods=(maintenance,),
        eligible_entry_bar_closes=(
            datetime(2026, 7, 27, 5, 45, tzinfo=timezone.utc),
            datetime(2026, 7, 27, 5, 50, tzinfo=timezone.utc),
        ),
    )
    resolution = authority_resolution(
        kind=AuthorityKind.EXCHANGE_SESSION,
        status=AuthorityStatus.AVAILABLE,
        evaluated_at=AT,
        effective_interval=EffectiveInterval(
            request.candidate_closed_at, inputs.session_ends_at
        ),
        source=source(),
        value=inputs,
    )
    result = validate_exchange_session(request, resolution)
    assert result.status == AuthorityStatus.CONFLICTING
    assert result.reasons == (AuthorityReason.EXCHANGE_SESSION_MISMATCH,)


def test_trade_plan_policy_must_retain_authoritative_p2a_identity():
    request = TradePlanPolicyAuthorityRequest(
        product(), "displacement_volume_context", "1.0.0", AT
    )
    resolution = authority_resolution(
        kind=AuthorityKind.TRADE_PLAN_POLICY,
        status=AuthorityStatus.AVAILABLE,
        evaluated_at=AT,
        effective_interval=interval(),
        source=source(),
        value=policy(),
    )
    assert validate_trade_plan_policy(request, resolution).status == (
        AuthorityStatus.AVAILABLE
    )


def state(index: int) -> MarketState:
    occurred = AT - timedelta(minutes=5 * (288 - index))
    return MarketState(
        envelope=Event(
            event_id=f"event-{index:03d}",
            event_type="bar_closed",
            source="tradingview",
            occurred_at=occurred,
            received_at=occurred + timedelta(seconds=1),
        ),
        schema_version="1.0",
        symbol=Symbol("MNQ1!"),
        timeframe=Timeframe.M5,
        bar_status=BarStatus.CLOSED,
    )


def market_window(count: int = 288) -> MarketInputWindow:
    states = tuple(state(index) for index in range(count))
    events = tuple(
        SourceEventIdentity(
            event_id=item.envelope.event_id,
            event_type=item.envelope.event_type,
            source=item.envelope.source,
            schema_version=item.schema_version,
            occurred_at=item.envelope.occurred_at,
            received_at=item.envelope.received_at,
        )
        for item in states
    )
    identity = MarketInputIdentity(
        economic_instrument=product(),
        market_data_series=series(),
        listed_instrument=None,
        timeframe="5m",
        strategy_id="displacement_volume_context",
        strategy_version="1.0.0",
        latest_closed_at=states[-1].envelope.occurred_at,
        observed_at=AT,
        bar_count=count,
        source_events=events,
        source_schema_versions=("1.0",),
    )
    available = MarketSourceAvailability(AvailabilityStatus.AVAILABLE, (), AT)
    return MarketInputWindow(available, available, identity, states)


def test_canonical_market_adapter_requires_and_preserves_exactly_288_events():
    result = adapt_canonical_market_input(market_window(), source=source())
    assert result.status == AuthorityStatus.AVAILABLE
    assert result.value is not None
    assert result.value.market_input.bar_count == 288
    assert len(result.value.source_event_ids) == 288
    assert result.value.latest_source_event.event_id == "event-287"
    assert result.value.timeframe == "5m"
    assert result.value.expected_cadence_seconds == 300


def test_canonical_market_adapter_rejects_a_gapped_288_event_window():
    window = market_window()
    shifted_states = tuple(
        replace(
            item,
            envelope=replace(
                item.envelope,
                occurred_at=item.envelope.occurred_at
                + (timedelta(hours=1) if index >= 144 else timedelta()),
                received_at=item.envelope.received_at
                + (timedelta(hours=1) if index >= 144 else timedelta()),
            ),
        )
        for index, item in enumerate(window.states)
    )
    shifted_events = tuple(
        SourceEventIdentity(
            event_id=item.envelope.event_id,
            event_type=item.envelope.event_type,
            source=item.envelope.source,
            schema_version=item.schema_version,
            occurred_at=item.envelope.occurred_at,
            received_at=item.envelope.received_at,
        )
        for item in shifted_states
    )
    assert window.identity is not None
    identity = replace(
        window.identity,
        latest_closed_at=shifted_events[-1].occurred_at,
        source_events=shifted_events,
    )
    result = adapt_canonical_market_input(
        replace(window, identity=identity, states=shifted_states),
        source=source(),
    )
    assert result.status == AuthorityStatus.CONFLICTING
    assert result.value is None
    assert result.reasons == (AuthorityReason.MARKET_CADENCE_INVALID,)


def test_noncanonical_market_history_fails_closed():
    result = adapt_canonical_market_input(market_window(287), source=source())
    assert result.status == AuthorityStatus.UNAVAILABLE
    assert result.value is None
    assert result.reasons == (AuthorityReason.MARKET_HISTORY_NOT_CANONICAL,)


def test_market_source_event_disagreement_fails_closed():
    window = market_window()
    assert window.identity is not None
    changed = replace(
        window.identity.source_events[-1],
        event_id="conflicting-event",
    )
    identity = replace(
        window.identity,
        source_events=window.identity.source_events[:-1] + (changed,),
    )
    result = adapt_canonical_market_input(
        replace(window, identity=identity), source=source()
    )
    assert result.status == AuthorityStatus.CONFLICTING
    assert result.value is None
    assert result.reasons == (AuthorityReason.SOURCE_EVENT_MISMATCH,)


def test_duplicate_source_event_identity_fails_closed_without_exception():
    window = market_window()
    assert window.identity is not None
    duplicate_id = window.identity.source_events[-2].event_id
    changed_state = replace(
        window.states[-1],
        envelope=replace(window.states[-1].envelope, event_id=duplicate_id),
    )
    changed_event = replace(window.identity.source_events[-1], event_id=duplicate_id)
    result = adapt_canonical_market_input(
        replace(
            window,
            identity=replace(
                window.identity,
                source_events=window.identity.source_events[:-1] + (changed_event,),
            ),
            states=window.states[:-1] + (changed_state,),
        ),
        source=source(),
    )
    assert result.status == AuthorityStatus.CONFLICTING
    assert result.reasons == (AuthorityReason.SOURCE_EVENT_ORDER_INVALID,)


def test_non_monotonic_source_events_fail_closed_without_exception():
    window = market_window()
    assert window.identity is not None
    earlier = window.identity.source_events[-2].occurred_at - timedelta(minutes=1)
    changed_state = replace(
        window.states[-1],
        envelope=replace(
            window.states[-1].envelope,
            occurred_at=earlier,
            received_at=earlier + timedelta(seconds=1),
        ),
    )
    changed_event = replace(
        window.identity.source_events[-1],
        occurred_at=earlier,
        received_at=earlier + timedelta(seconds=1),
    )
    result = adapt_canonical_market_input(
        replace(
            window,
            identity=replace(
                window.identity,
                latest_closed_at=earlier,
                source_events=window.identity.source_events[:-1] + (changed_event,),
            ),
            states=window.states[:-1] + (changed_state,),
        ),
        source=source(),
    )
    assert result.status == AuthorityStatus.CONFLICTING
    assert result.reasons == (AuthorityReason.SOURCE_EVENT_ORDER_INVALID,)


def test_market_adapter_rejects_future_and_unreconciled_authority():
    future = adapt_canonical_market_input(
        market_window(),
        source=source(
            observed_at=AT + timedelta(seconds=1),
            retrieved_at=AT + timedelta(seconds=2),
        ),
    )
    unreconciled = adapt_canonical_market_input(
        market_window(), source=source(reconciled=False)
    )
    assert future.reasons == (AuthorityReason.FUTURE_DATED,)
    assert unreconciled.reasons == (AuthorityReason.UNRECONCILED,)


def test_context_insufficient_history_closes_an_available_market_resolution():
    available = adapt_canonical_market_input(market_window(), source=source())
    refused = require_sufficient_context_history(available, sufficient=False)
    assert refused.status == AuthorityStatus.UNAVAILABLE
    assert refused.value is None
    assert refused.reasons == (AuthorityReason.CONTEXT_INSUFFICIENT_HISTORY,)
    assert require_sufficient_context_history(available, sufficient=True) is available


def test_resolution_identity_normalizes_equivalent_instants_to_utc():
    utc = listed_resolution()
    offset = timezone(timedelta(hours=3))
    equivalent = authority_resolution(
        kind=AuthorityKind.LISTED_CONTRACT,
        status=AuthorityStatus.AVAILABLE,
        evaluated_at=AT.astimezone(offset),
        effective_interval=EffectiveInterval(
            START.astimezone(offset), END.astimezone(offset)
        ),
        source=replace(
            source(),
            observed_at=source().observed_at.astimezone(offset),
            retrieved_at=source().retrieved_at.astimezone(offset),
        ),
        value=listed(),
    )
    assert equivalent.resolution_id == utc.resolution_id
    assert canonical_bytes(equivalent) == canonical_bytes(utc)


@pytest.mark.parametrize(
    ("status", "reason"),
    (
        (AuthorityStatus.UNAVAILABLE, AuthorityReason.CONFLICTING),
        (AuthorityStatus.STALE, AuthorityReason.MISSING),
        (AuthorityStatus.CONFLICTING, AuthorityReason.MISSING),
    ),
)
def test_resolution_rejects_status_reason_mismatch(status, reason):
    with pytest.raises(ValueError, match="incompatible reason"):
        listed_resolution(status=status, reasons=(reason,))


def test_unknown_interval_cannot_be_used_as_available_authority():
    with pytest.raises(ValueError, match="effective"):
        authority_resolution(
            kind=AuthorityKind.LISTED_CONTRACT,
            status=AuthorityStatus.AVAILABLE,
            evaluated_at=AT,
            effective_interval=EffectiveInterval(None, None),
            source=source(),
            value=listed(),
        )


def test_contracts_expose_no_partial_trade_geometry():
    fields = {
        field
        for contract in (
            AuthorityResolution,
            AuthoritySource,
            EffectiveInterval,
            ListedContractAuthorityRequest,
            InstrumentSpecificationAuthorityRequest,
            ExchangeSessionAuthorityRequest,
            PlanExpiryInputs,
            TradePlanPolicyAuthorityRequest,
        )
        for field in contract.__dataclass_fields__
    }
    assert (
        not {"entry", "stop", "target", "invalidation", "confidence", "quantity"}
        & fields
    )
