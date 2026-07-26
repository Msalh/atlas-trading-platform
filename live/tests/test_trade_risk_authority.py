import json
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from atlas.core.primitives import Price
from atlas.risk_assessment.models import (
    AccountSnapshot,
    InstrumentSpecification,
    KillSwitchStatus,
    PositionSide,
    PositionSnapshot,
    ReconciliationStatus,
    RiskAssessmentInput,
    RiskAuthority,
    RiskPolicy,
    SizingMode,
    SnapshotFreshnessPolicy,
    SourceProvenance,
)
from atlas.strategy_engine.models import (
    StrategyDecision,
    StrategyDirection,
    StrategyDisposition,
)
from atlas.trade_risk_authority import (
    AlignmentReason,
    AuthoritativeValue,
    AuthorityMetadata,
    ProposedTrade,
    QuantityResolution,
    SourceAuthority,
    StrategyCandidateIdentity,
    serialize_proposed_trade,
    to_candidate_trade_input,
    validate_proposal,
    validate_risk_input_alignment,
)
from atlas.trader_now.models import (
    EconomicInstrument,
    ListedInstrument,
    MarketDataProvider,
    MarketDataSeries,
    MarketDataSeriesType,
)

EVALUATED_AT = datetime(2026, 7, 24, 14, 0, tzinfo=timezone.utc)


def provenance(kind: str, name: str) -> SourceProvenance:
    return SourceProvenance(kind, "fixture.v1", name, "1")


def strategy_decision(**changes) -> StrategyDecision:
    return replace(
        StrategyDecision(
            occurred_at=EVALUATED_AT,
            strategy_id="displacement_volume_context",
            strategy_version="1.0.0",
            disposition=StrategyDisposition.CANDIDATE,
            direction=StrategyDirection.LONG,
            setup_ids=("setup-1",),
            reason_codes=(),
            context_fingerprint="context-1",
        ),
        **changes,
    )


def risk_policy(**changes) -> RiskPolicy:
    return replace(
        RiskPolicy(
            policy_id="policy-1",
            policy_version="1",
            account_profile_id="profile-1",
            authority=RiskAuthority.ADVISORY,
            sizing_mode=SizingMode.FIXED,
            freshness_policy_id="freshness-1",
            maximum_quantity=5,
            maximum_open_position_quantity=5,
            maximum_working_order_quantity=5,
            maximum_concurrent_positions=1,
            minimum_remaining_daily_risk=Decimal(100),
            daily_loss_limit=Decimal(1000),
            trailing_drawdown_limit=None,
            block_same_direction_additions=True,
            block_opposite_positions=True,
            working_orders_count_as_exposure=True,
            require_target=False,
            enforce_margin=False,
            no_trade_account_statuses=("restricted",),
            eligible_session_ids=("session-1",),
            provenance=provenance("policy", "policy-1"),
            maximum_risk_per_trade=Decimal(200),
        ),
        **changes,
    )


def assessment_input(**changes) -> RiskAssessmentInput:
    account = AccountSnapshot(
        snapshot_id="account-1",
        account_id="account-1",
        provider_id="provider-1",
        observed_at=EVALUATED_AT,
        received_at=EVALUATED_AT,
        effective_session_id="session-1",
        currency="USD",
        net_liquidation=Decimal(50000),
        daily_realized_pnl=Decimal(0),
        account_status="active",
        kill_switch_status=KillSwitchStatus.INACTIVE,
        reconciliation_status=ReconciliationStatus.RECONCILED,
        provenance=provenance("account", "account-1"),
    )
    position = PositionSnapshot(
        snapshot_id="position-1",
        account_id="account-1",
        product="MNQ",
        contract_symbol="MNQU6",
        side=PositionSide.FLAT,
        net_quantity=0,
        observed_at=EVALUATED_AT,
        received_at=EVALUATED_AT,
        broker_position_status="flat",
        reconciliation_status=ReconciliationStatus.RECONCILED,
        provenance=provenance("position", "position-1"),
    )
    instrument = InstrumentSpecification(
        specification_id="instrument-1",
        product="MNQ",
        contract_symbol="MNQU6",
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
        session_calendar_id="cme-rth-v1",
        provenance=provenance("instrument", "instrument-1"),
    )
    freshness = SnapshotFreshnessPolicy(
        policy_id="freshness-1",
        policy_version="1",
        account_max_age_seconds=Decimal(30),
        position_max_age_seconds=Decimal(30),
        candidate_max_age_seconds=Decimal(30),
        max_source_receive_delay_seconds=Decimal(5),
        allowed_future_skew_seconds=Decimal(2),
        require_same_session=True,
        provenance=provenance("freshness", "freshness-1"),
    )
    value = RiskAssessmentInput(
        input_id="input-1",
        snapshot_id="snapshot-1",
        strategy_decision=strategy_decision(),
        candidate=to_candidate_trade_input(proposal()),
        freshness_policy=freshness,
        evaluated_at=EVALUATED_AT,
        effective_session_id="session-1",
        latest_closed_at=EVALUATED_AT,
        account=account,
        positions=(position,),
        instrument=instrument,
        policy=risk_policy(),
    )
    return replace(value, **changes)


def proposal(**changes) -> ProposedTrade:
    strategy = strategy_decision()
    product = EconomicInstrument("MNQ")
    value = ProposedTrade(
        proposal_id="proposal-1",
        candidate=StrategyCandidateIdentity.from_decision(strategy),
        economic_instrument=product,
        analysis_series=MarketDataSeries(
            economic_instrument=product,
            provider=MarketDataProvider.TRADINGVIEW,
            symbol="MNQ1!",
            series_type=MarketDataSeriesType.CONTINUOUS,
            resolved_at=EVALUATED_AT,
            resolution_version="tradingview-mnq1.v1",
            resolution_owner="market-data-configuration",
        ),
        listed_instrument=ListedInstrument(
            economic_instrument=product,
            venue="CME",
            contract_symbol="MNQU6",
            expiry="2026-09",
        ),
        direction=StrategyDirection.LONG,
        entry_type="limit",
        entry=Price(20_000, 0.25),
        stop=Price(19_990, 0.25),
        target=Price(20_020, 0.25),
        invalidation=Price(19_989, 0.25),
        quantity_resolution=QuantityResolution.RESOLVED,
        requested_quantity=1,
        created_at=EVALUATED_AT,
        evaluated_at=EVALUATED_AT,
        rule_id="proposal-rule",
        rule_version="1.0.0",
        authority=AuthorityMetadata(
            authority=SourceAuthority.AUTHORITATIVE,
            provenance=provenance("p2a", "proposal"),
            observed_at=EVALUATED_AT,
            received_at=EVALUATED_AT,
            reconciled=True,
        ),
    )
    return replace(value, **changes)


def validate(value: ProposedTrade, **changes):
    return validate_proposal(
        strategy=changes.pop("strategy", strategy_decision()),
        proposal=value,
        policy=changes.pop("policy", risk_policy(require_target=True)),
        evaluated_at=changes.pop("evaluated_at", EVALUATED_AT),
        maximum_age_seconds=changes.pop("maximum_age_seconds", Decimal(30)),
        **changes,
    )


def test_golden_proposal_is_immutable_deterministic_and_aligns_losslessly():
    value = proposal()
    assert validate(value).accepted
    assert serialize_proposed_trade(value) == serialize_proposed_trade(value)
    serialized = json.loads(serialize_proposed_trade(value))
    assert serialized["entry"] == {"tick_size": "0.25", "value": "20000"}
    assert serialized["analysis_series"]["symbol"] == "MNQ1!"
    assert serialized["listed_instrument"]["contract_symbol"] == "MNQU6"
    with pytest.raises(FrozenInstanceError):
        value.proposal_id = "changed"  # type: ignore[misc]

    candidate = to_candidate_trade_input(value)
    assert candidate.product == "MNQ"
    assert candidate.contract_symbol == "MNQU6"
    assert candidate.contract_symbol != value.analysis_series.symbol
    assert candidate.strategy_id == value.candidate.strategy_id
    assert candidate.entry is value.entry
    assert candidate.stop is value.stop


def test_continuous_series_can_never_be_the_listed_contract():
    base = proposal()
    with pytest.raises(ValueError, match="continuous analysis series"):
        replace(
            base,
            listed_instrument=replace(
                base.listed_instrument, contract_symbol="MNQ1!"
            ),
        )


@pytest.mark.parametrize(
    ("change", "validation_change", "reason"),
    [
        (
            {"quantity_resolution": QuantityResolution.UNRESOLVED, "requested_quantity": None},
            {},
            AlignmentReason.QUANTITY_UNRESOLVED,
        ),
        (
            {},
            {"evaluated_at": EVALUATED_AT + timedelta(seconds=31)},
            AlignmentReason.PROPOSAL_STALE,
        ),
        (
            {
                "created_at": EVALUATED_AT + timedelta(seconds=1),
                "evaluated_at": EVALUATED_AT + timedelta(seconds=1),
            },
            {},
            AlignmentReason.PROPOSAL_FUTURE,
        ),
    ],
)
def test_fail_closed_proposal_states(change, validation_change, reason):
    assert reason in validate(proposal(**change), **validation_change).reasons


def test_target_requirement_is_policy_owned():
    value = proposal(target=None)
    assert AlignmentReason.TARGET_REQUIRED in validate(value).reasons
    assert validate(value, policy=risk_policy(require_target=False)).accepted


def test_unresolved_quantity_is_allowed_only_for_explicit_risk_based_policy():
    value = proposal(
        quantity_resolution=QuantityResolution.UNRESOLVED,
        requested_quantity=None,
    )
    assert AlignmentReason.QUANTITY_UNRESOLVED in validate(value).reasons
    assert validate(
        value,
        policy=risk_policy(
            sizing_mode=SizingMode.RISK_BASED,
            maximum_risk_per_trade=Decimal(200),
        ),
    ).accepted


def test_non_authoritative_and_unreconciled_metadata_refuse():
    base = proposal()
    configured = replace(
        base.authority,
        authority=SourceAuthority.CONFIGURED,
        reconciled=False,
    )
    result = validate(replace(base, authority=configured))
    assert result.reasons == (
        AlignmentReason.SOURCE_NOT_AUTHORITATIVE,
        AlignmentReason.SOURCE_UNRECONCILED,
    )
    with pytest.raises(ValueError, match="authoritative.*reconciled"):
        replace(base.authority, reconciled=False)


def test_authoritative_value_makes_absence_and_authority_explicit():
    unavailable = AuthorityMetadata(
        authority=SourceAuthority.UNAVAILABLE,
        provenance=provenance("p2a", "unavailable"),
        observed_at=EVALUATED_AT,
        received_at=EVALUATED_AT,
        reconciled=False,
    )
    assert AuthoritativeValue(value=None, metadata=unavailable).value is None
    with pytest.raises(ValueError, match="must not carry"):
        AuthoritativeValue(value="invented", metadata=unavailable)
    with pytest.raises(ValueError, match="requires a value"):
        AuthoritativeValue(value=None, metadata=proposal().authority)


def test_cross_candidate_and_non_candidate_refuse():
    base = proposal()
    other = replace(strategy_decision(), context_fingerprint="other")
    assert AlignmentReason.CANDIDATE_IDENTITY_MISMATCH in validate(
        base, strategy=other
    ).reasons
    rejected = StrategyDecision(
        occurred_at=EVALUATED_AT,
        strategy_id="displacement_volume_context",
        strategy_version="1.0.0",
        disposition=StrategyDisposition.REJECTED,
        direction=StrategyDirection.FLAT,
        setup_ids=("setup-1",),
        reason_codes=("failed",),
        context_fingerprint="context-1",
    )
    assert AlignmentReason.STRATEGY_NOT_CANDIDATE in validate(
        base, strategy=rejected
    ).reasons


def test_risk_input_requires_exact_candidate_and_instrument_alignment():
    value = proposal()
    base = assessment_input(
        strategy_decision=strategy_decision(),
        candidate=to_candidate_trade_input(value),
    )
    assert validate_risk_input_alignment(value, base).accepted

    conflicting = replace(
        base,
        candidate=replace(base.candidate, context_fingerprint="other"),
    )
    assert validate_risk_input_alignment(value, conflicting).reasons == (
        AlignmentReason.RISK_INPUT_MISMATCH,
    )
    cross_instrument = replace(
        base,
        instrument=replace(base.instrument, contract_symbol="MNQZ6"),
    )
    assert validate_risk_input_alignment(value, cross_instrument).reasons == (
        AlignmentReason.LISTED_INSTRUMENT_MISMATCH,
    )


def test_timestamps_and_candidate_identity_reject_invalid_construction():
    with pytest.raises(ValueError, match="received_at"):
        AuthorityMetadata(
            authority=SourceAuthority.CONFIGURED,
            provenance=provenance("p2a", "bad"),
            observed_at=EVALUATED_AT,
            received_at=EVALUATED_AT - timedelta(seconds=1),
            reconciled=False,
        )
    with pytest.raises(ValueError, match="unique"):
        StrategyCandidateIdentity(
            occurred_at=EVALUATED_AT,
            strategy_id="strategy",
            strategy_version="1",
            setup_ids=("same", "same"),
            context_fingerprint="context",
            direction=StrategyDirection.LONG,
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(proposal(), created_at=datetime(2026, 7, 24))  # noqa: DTZ001
    with pytest.raises(ValueError, match="candidate"):
        replace(proposal(), created_at=EVALUATED_AT - timedelta(microseconds=1))
    with pytest.raises(ValueError, match="provenance"):
        replace(
            proposal(),
            authority=replace(
                proposal().authority,
                observed_at=EVALUATED_AT + timedelta(microseconds=1),
                received_at=EVALUATED_AT + timedelta(microseconds=1),
            ),
        )


def test_risk_vocabulary_is_not_duplicated():
    from atlas.risk_assessment.models import AssessmentStatus

    assert {item.value for item in AssessmentStatus} == {
        "approved",
        "blocked",
        "unassessable",
        "not_applicable",
    }
