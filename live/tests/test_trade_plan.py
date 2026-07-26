import hashlib
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from atlas.risk_assessment.models import (
    InstrumentSpecification,
    SizingMode,
    SourceProvenance,
)
from atlas.strategy_engine.models import (
    StrategyDecision,
    StrategyDirection,
    StrategyDisposition,
)
from atlas.trade_plan import (
    CandidateBarEvidence,
    EvidenceAvailability,
    TradePlanEvidenceBinding,
    TradePlanInput,
    TradePlanPolicy,
    TradePlanPurpose,
    TradePlanRefusalReason,
    TradePlanStatus,
    build_trade_plan,
    canonical_bytes,
)
from atlas.trade_risk_authority import (
    AuthorityMetadata,
    SourceAuthority,
    StrategyCandidateIdentity,
    to_candidate_trade_input,
    validate_proposal,
)
from atlas.trader_now.models import (
    EconomicInstrument,
    ListedInstrument,
    MarketDataProvider,
    MarketDataSeries,
    MarketDataSeriesType,
    MarketInputIdentity,
    SourceEventIdentity,
)
from tests.risk_assessment_fixtures import risk_policy

AT = datetime(2026, 7, 24, 14, 0, tzinfo=timezone.utc)


def provenance(kind: str, object_id: str) -> SourceProvenance:
    return SourceProvenance(kind, "test-only.v1", object_id, "1")


def authority(kind: str, object_id: str) -> AuthorityMetadata:
    return AuthorityMetadata(
        SourceAuthority.AUTHORITATIVE,
        provenance(kind, object_id),
        AT,
        AT,
        True,
    )


def strategy(direction: StrategyDirection = StrategyDirection.LONG, **changes) -> StrategyDecision:
    return replace(
        StrategyDecision(
            occurred_at=AT,
            strategy_id="displacement_volume_context",
            strategy_version="1.0.0",
            disposition=StrategyDisposition.CANDIDATE,
            direction=direction,
            setup_ids=("test-setup-1",),
            reason_codes=(),
            context_fingerprint="test-context-1",
        ),
        **changes,
    )


def source_event(**changes) -> SourceEventIdentity:
    return replace(
        SourceEventIdentity(
            event_id="test-event-1",
            event_type="bar_closed",
            source="test-only-tradingview",
            schema_version="market_state.v1",
            occurred_at=AT,
            received_at=AT,
        ),
        **changes,
    )


def trade_input(direction: StrategyDirection = StrategyDirection.LONG, **changes) -> TradePlanInput:
    product = EconomicInstrument("MNQ")
    series = MarketDataSeries(
        economic_instrument=product,
        provider=MarketDataProvider.TRADINGVIEW,
        symbol="MNQ1!",
        series_type=MarketDataSeriesType.CONTINUOUS,
        resolved_at=AT,
        resolution_version="test-only-mnq1.v1",
        resolution_owner="test-fixture",
    )
    event = source_event()
    market = MarketInputIdentity(
        economic_instrument=product,
        market_data_series=series,
        listed_instrument=None,
        timeframe="5m",
        strategy_id="displacement_volume_context",
        strategy_version="1.0.0",
        latest_closed_at=AT,
        observed_at=AT,
        bar_count=1,
        source_events=(event,),
        source_schema_versions=("market_state.v1",),
    )
    evidence = TradePlanEvidenceBinding(
        market_input=market,
        candidate=StrategyCandidateIdentity.from_decision(strategy(direction)),
        candidate_bar=CandidateBarEvidence(
            event,
            Decimal("20000.00"),
            Decimal("20001.25"),
            Decimal("19999.00"),
            Decimal("20000.50"),
        ),
        rules=EvidenceAvailability.AVAILABLE,
        setups=EvidenceAvailability.AVAILABLE,
        interpretation=EvidenceAvailability.AVAILABLE,
        context=EvidenceAvailability.AVAILABLE,
        effective_session_id="test-session-2026-07-24",
        entry_bar_closes=(AT + timedelta(minutes=5), AT + timedelta(minutes=10)),
        session_ends_at=AT + timedelta(hours=7),
        authority=authority("evidence", "test-event-1"),
    )
    listed = ListedInstrument(product, "CME", "TEST-MNQU6", "2026-09")
    specification = InstrumentSpecification(
        specification_id="test-only-mnq-specification",
        product="MNQ",
        contract_symbol="TEST-MNQU6",
        asset_class="future",
        exchange="CME",
        currency="USD",
        tick_size=Decimal("0.25"),
        tick_value=Decimal("0.50"),
        point_value=Decimal(2),
        contract_multiplier=Decimal(2),
        minimum_quantity=1,
        quantity_increment=1,
        price_precision=2,
        session_calendar_id="test-only-calendar",
        provenance=provenance("instrument", "test-only-mnq-specification"),
    )
    policy = TradePlanPolicy(
        policy_id="test-only-trade-plan-policy",
        policy_version="1",
        geometry_rule_id="candidate-bar-break.v1",
        geometry_rule_version="1",
        reward_multiple=Decimal("1.9"),
        maximum_entry_bars=2,
        maximum_evidence_age_seconds=Decimal(120),
        authority=authority("policy", "test-only-trade-plan-policy"),
    )
    value = TradePlanInput(
        strategy=strategy(direction),
        evidence=evidence,
        listed_instrument=listed,
        instrument_specification=specification,
        instrument_authority=authority("instrument", specification.specification_id),
        policy=policy,
        evaluated_at=AT + timedelta(minutes=1),
    )
    return replace(value, **changes)


@pytest.mark.parametrize(
    ("direction", "entry", "invalidation", "stop", "target"),
    [
        (StrategyDirection.LONG, 20001.5, 19999.0, 19998.75, 20006.5),
        (StrategyDirection.SHORT, 19998.75, 20001.25, 20001.5, 19993.75),
    ],
)
def test_mirrored_geometry_uses_decimal_directional_and_conservative_rounding(
    direction, entry, invalidation, stop, target
):
    result = build_trade_plan(trade_input(direction))
    assert result.status == TradePlanStatus.GENERATED
    assert result.refusal is None
    assert result.success is not None
    proposal = result.success.proposed_trade
    assert (proposal.entry.value, proposal.invalidation.value) == (entry, invalidation)
    assert (proposal.stop.value, proposal.target.value) == (stop, target)
    assert proposal.entry.tick_size == proposal.stop.tick_size == 0.25
    assert proposal.requested_quantity is None
    assert result.success.purpose == TradePlanPurpose.ANALYSIS_ONLY
    assert result.success.execution_eligible is False
    assert result.success.requires_risk_assessment
    assert result.success.requires_separate_decision


def test_plan_identity_and_canonical_bytes_are_stable_and_p2a_compatible():
    first = build_trade_plan(trade_input())
    second = build_trade_plan(trade_input())
    assert first == second
    assert canonical_bytes(first) == canonical_bytes(second)
    assert first.success is not None
    assert len(first.success.plan_id) == 64
    candidate = to_candidate_trade_input(first.success.proposed_trade)
    assert candidate.candidate_id == first.success.plan_id
    assert candidate.contract_symbol == "TEST-MNQU6"
    assert candidate.requested_quantity is None
    assert validate_proposal(
        strategy=trade_input().strategy,
        proposal=first.success.proposed_trade,
        policy=risk_policy(sizing_mode=SizingMode.RISK_BASED, require_target=True),
        evaluated_at=trade_input().evaluated_at,
        maximum_age_seconds=Decimal(120),
    ).accepted
    with pytest.raises(FrozenInstanceError):
        first.success.plan_id = "changed"  # type: ignore[misc]


def test_golden_plan_identity_and_result_bytes_are_frozen():
    result = build_trade_plan(trade_input())
    payload = canonical_bytes(result)
    assert result.success is not None
    assert result.success.plan_id == (
        "13f972254fb01018748b300ba8c38568bf7f99cf6396c2843d9a27a7c3f16dd7"
    )
    assert hashlib.sha256(payload).hexdigest() == (
        "1d02de022cf2cf6578e95d9edf9f4e9d1aa31c43b775c0e2c712452ac1bbd3cd"
    )
    assert len(payload) == 3931


def test_identity_changes_for_every_authoritative_identity_input():
    base = trade_input()
    baseline = build_trade_plan(base).success
    assert baseline is not None

    changed_event = replace(base.evidence.candidate_bar.source_event, event_id="test-event-2")
    changed_market = replace(base.evidence.market_input, source_events=(changed_event,))
    event_input = replace(
        base,
        evidence=replace(
            base.evidence,
            candidate_bar=replace(base.evidence.candidate_bar, source_event=changed_event),
            market_input=changed_market,
            authority=replace(
                base.evidence.authority,
                provenance=replace(
                    base.evidence.authority.provenance,
                    source_object_id="test-event-2",
                ),
            ),
        ),
    )
    candidate_input = replace(
        base,
        strategy=replace(base.strategy, context_fingerprint="test-context-2"),
    )
    candidate_input = replace(
        candidate_input,
        evidence=replace(
            candidate_input.evidence,
            candidate=replace(
                candidate_input.evidence.candidate,
                context_fingerprint="test-context-2",
            ),
        ),
    )
    listed = replace(base.listed_instrument, contract_symbol="TEST-MNQZ6")
    listed_input = replace(
        base,
        listed_instrument=listed,
        instrument_specification=replace(
            base.instrument_specification, contract_symbol="TEST-MNQZ6"
        ),
    )
    spec_input = replace(
        base,
        instrument_specification=replace(
            base.instrument_specification, specification_id="test-only-mnq-specification-2"
        ),
        instrument_authority=replace(
            base.instrument_authority,
            provenance=replace(
                base.instrument_authority.provenance,
                source_object_id="test-only-mnq-specification-2",
            ),
        ),
    )
    policy_input = replace(
        base,
        policy=replace(base.policy, policy_id="test-only-trade-plan-policy-2"),
        # Policy authority must bind the changed policy identity.
    )
    policy_input = replace(
        policy_input,
        policy=replace(
            policy_input.policy,
            authority=replace(
                policy_input.policy.authority,
                provenance=replace(
                    policy_input.policy.authority.provenance,
                    source_object_id="test-only-trade-plan-policy-2",
                ),
            ),
        ),
    )
    results = [build_trade_plan(item) for item in (
        event_input, candidate_input, listed_input, spec_input, policy_input
    )]
    ids = [item.success.plan_id for item in results if item.success is not None]
    assert len(ids) == 5
    assert len(set(ids + [baseline.plan_id])) == 6


@pytest.mark.parametrize(
    ("mutator", "reason"),
    [
        (lambda value: replace(value, listed_instrument=None), TradePlanRefusalReason.LISTED_INSTRUMENT_MISSING),
        (
            lambda value: replace(
                value,
                listed_instrument=replace(value.listed_instrument, contract_symbol="MNQ1!"),
                instrument_specification=replace(value.instrument_specification, contract_symbol="MNQ1!"),
            ),
            TradePlanRefusalReason.CONTINUOUS_SERIES_AS_CONTRACT,
        ),
        (lambda value: replace(value, instrument_specification=None), TradePlanRefusalReason.SPECIFICATION_MISSING),
        (
            lambda value: replace(
                value,
                instrument_specification=replace(
                    value.instrument_specification, contract_symbol="TEST-MNQZ6"
                ),
            ),
            TradePlanRefusalReason.SPECIFICATION_MISMATCH,
        ),
        (
            lambda value: replace(
                value,
                evidence=replace(value.evidence, context=EvidenceAvailability.INSUFFICIENT),
            ),
            TradePlanRefusalReason.CONTEXT_UNAVAILABLE,
        ),
        (
            lambda value: replace(
                value,
                evidence=replace(value.evidence, rules=EvidenceAvailability.CONFLICTING),
            ),
            TradePlanRefusalReason.RULES_UNAVAILABLE,
        ),
        (
            lambda value: replace(
                value,
                evidence=replace(
                    value.evidence,
                    authority=replace(
                        value.evidence.authority,
                        authority=SourceAuthority.CONFIGURED,
                        reconciled=False,
                    ),
                ),
            ),
            TradePlanRefusalReason.SOURCE_NOT_AUTHORITATIVE,
        ),
        (
            lambda value: replace(value, policy=None),
            TradePlanRefusalReason.POLICY_MISSING,
        ),
        (
            lambda value: replace(value, evaluated_at=AT + timedelta(minutes=3)),
            TradePlanRefusalReason.EVIDENCE_STALE,
        ),
        (
            lambda value: replace(
                value,
                strategy=replace(value.strategy, context_fingerprint="other"),
            ),
            TradePlanRefusalReason.CANDIDATE_MISMATCH,
        ),
        (
            lambda value: replace(
                value,
                strategy=replace(
                    value.strategy,
                    stop=value.instrument_specification
                    and __import__("atlas.core.primitives", fromlist=["Price"]).Price(19998.75, 0.25),
                ),
            ),
            TradePlanRefusalReason.STRATEGY_GEOMETRY_CONFLICT,
        ),
        (
            lambda value: replace(
                value,
                policy=replace(value.policy, reward_multiple=Decimal("0.01")),
            ),
            TradePlanRefusalReason.ROUNDING_COLLAPSE,
        ),
        (
            lambda value: replace(
                value,
                evidence=replace(
                    value.evidence,
                    candidate_bar=replace(
                        value.evidence.candidate_bar, high=Decimal("20001.13")
                    ),
                ),
            ),
            TradePlanRefusalReason.GEOMETRY_INVALID,
        ),
    ],
)
def test_negative_and_adversarial_inputs_refuse_without_partial_output(mutator, reason):
    result = build_trade_plan(mutator(trade_input()))
    assert result.status == TradePlanStatus.REFUSED
    assert result.success is None
    assert result.refusal is not None
    assert reason in result.refusal.reasons
    assert b'"entry"' not in canonical_bytes(result)
    assert b'"target"' not in canonical_bytes(result)


def test_expiry_uses_earlier_bar_count_or_session_boundary_and_is_explicit():
    value = trade_input()
    bar_expiry = build_trade_plan(value).success
    assert bar_expiry is not None
    assert bar_expiry.expires_at == AT + timedelta(minutes=10)
    session = replace(
        value,
        evidence=replace(value.evidence, session_ends_at=AT + timedelta(minutes=7)),
    )
    session_expiry = build_trade_plan(session).success
    assert session_expiry is not None
    assert session_expiry.expires_at == AT + timedelta(minutes=7)
    mismatch = replace(
        value,
        evidence=replace(value.evidence, entry_bar_closes=(AT + timedelta(minutes=5),)),
    )
    refused = build_trade_plan(mismatch)
    assert refused.refusal is not None
    assert TradePlanRefusalReason.EXPIRY_INVALID in refused.refusal.reasons


def test_source_event_and_reconciliation_fail_closed():
    value = trade_input()
    other = replace(value.evidence.candidate_bar.source_event, event_id="other-event")
    mismatched = replace(
        value,
        evidence=replace(
            value.evidence,
            market_input=replace(value.evidence.market_input, source_events=(other,)),
        ),
    )
    result = build_trade_plan(mismatched)
    assert result.refusal is not None
    assert TradePlanRefusalReason.SOURCE_EVENT_MISMATCH in result.refusal.reasons
    assert result.success is None


def test_contracts_cannot_express_recommendation_order_or_execution_authority():
    payload = canonical_bytes(build_trade_plan(trade_input())).decode("utf-8").lower()
    for prohibited in (
        '"recommendation"',
        '"order"',
        '"broker"',
        '"enter"',
        '"wait"',
        '"prepare"',
        '"approved"',
        '"execution_instruction"',
    ):
        assert prohibited not in payload
    assert '"purpose":"analysis_only"' in payload
    assert '"execution_eligible":false' in payload
    assert '"authority":"proposed_geometry"' in payload
