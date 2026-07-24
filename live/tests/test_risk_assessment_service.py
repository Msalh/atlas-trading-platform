from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from atlas.core.primitives import Price
from atlas.risk_assessment.models import (
    AccountSnapshot,
    AssessmentStatus,
    CandidateTradeInput,
    FreshnessStatus,
    InstrumentSpecification,
    KillSwitchStatus,
    PositionSide,
    PositionSnapshot,
    ReconciliationStatus,
    RiskAssessmentInput,
    RiskAuthority,
    RiskPolicy,
    RiskReason,
    SizingMode,
    SnapshotFreshnessPolicy,
    SourceProvenance,
)
from atlas.risk_assessment.service import assess_candidate_risk
from atlas.strategy_engine.models import (
    StrategyDecision,
    StrategyDirection,
    StrategyDisposition,
)

NOW = datetime(2026, 7, 24, 14, 0, tzinfo=timezone.utc)
PROVENANCE = SourceProvenance("fixture", "v1", "fixture-1")


def _account(**changes) -> AccountSnapshot:
    value = AccountSnapshot(
        snapshot_id="account-snapshot-1",
        account_id="account-1",
        provider_id="provider-1",
        observed_at=NOW,
        received_at=NOW,
        effective_session_id="session-1",
        currency="USD",
        net_liquidation=Decimal("50000"),
        daily_realized_pnl=Decimal("0"),
        account_status="active",
        kill_switch_status=KillSwitchStatus.INACTIVE,
        reconciliation_status=ReconciliationStatus.RECONCILED,
        provenance=PROVENANCE,
        unrealized_pnl=Decimal("0"),
        high_water_mark=Decimal("50000"),
    )
    return replace(value, **changes)


def _position(**changes) -> PositionSnapshot:
    value = PositionSnapshot(
        snapshot_id="position-1",
        account_id="account-1",
        product="MNQ",
        contract_symbol="MNQU6",
        side=PositionSide.FLAT,
        net_quantity=0,
        observed_at=NOW,
        received_at=NOW,
        broker_position_status="flat",
        reconciliation_status=ReconciliationStatus.RECONCILED,
        provenance=PROVENANCE,
    )
    return replace(value, **changes)


def _instrument(**changes) -> InstrumentSpecification:
    value = InstrumentSpecification(
        specification_id="instrument-1",
        product="MNQ",
        contract_symbol="MNQU6",
        asset_class="future",
        exchange="CME",
        currency="USD",
        tick_size=Decimal("0.25"),
        tick_value=Decimal("0.50"),
        point_value=Decimal("2"),
        contract_multiplier=Decimal("2"),
        minimum_quantity=1,
        quantity_increment=1,
        price_precision=2,
        session_calendar_id="cme-rth-v1",
        provenance=PROVENANCE,
    )
    return replace(value, **changes)


def _freshness(**changes) -> SnapshotFreshnessPolicy:
    value = SnapshotFreshnessPolicy(
        policy_id="freshness-1",
        policy_version="1.0.0",
        account_max_age_seconds=Decimal("30"),
        position_max_age_seconds=Decimal("30"),
        candidate_max_age_seconds=Decimal("30"),
        max_source_receive_delay_seconds=Decimal("5"),
        allowed_future_skew_seconds=Decimal("2"),
        require_same_session=True,
        provenance=PROVENANCE,
    )
    return replace(value, **changes)


def _policy(**changes) -> RiskPolicy:
    value = RiskPolicy(
        policy_id="risk-1",
        policy_version="1.0.0",
        account_profile_id="profile-1",
        authority=RiskAuthority.ADVISORY,
        sizing_mode=SizingMode.FIXED,
        freshness_policy_id="freshness-1",
        maximum_quantity=5,
        maximum_open_position_quantity=5,
        maximum_working_order_quantity=5,
        maximum_concurrent_positions=1,
        minimum_remaining_daily_risk=Decimal("100"),
        daily_loss_limit=Decimal("1000"),
        trailing_drawdown_limit=Decimal("2000"),
        block_same_direction_additions=True,
        block_opposite_positions=True,
        working_orders_count_as_exposure=True,
        require_target=False,
        enforce_margin=False,
        no_trade_account_statuses=("restricted",),
        eligible_session_ids=("session-1",),
        provenance=PROVENANCE,
        maximum_risk_per_trade=Decimal("200"),
    )
    return replace(value, **changes)


def _strategy(**changes) -> StrategyDecision:
    value = StrategyDecision(
        occurred_at=NOW,
        strategy_id="displacement_volume_context",
        strategy_version="1.0.0",
        disposition=StrategyDisposition.CANDIDATE,
        direction=StrategyDirection.LONG,
        setup_ids=("setup-1",),
        reason_codes=(),
        context_fingerprint="context-1",
    )
    return replace(value, **changes)


def _candidate(**changes) -> CandidateTradeInput:
    value = CandidateTradeInput(
        candidate_id="candidate-1",
        strategy_id="displacement_volume_context",
        strategy_version="1.0.0",
        context_fingerprint="context-1",
        product="MNQ",
        contract_symbol="MNQU6",
        candidate_at=NOW,
        direction="long",
        entry_type="market",
        entry=Price(20_000, 0.25),
        stop=Price(19_990, 0.25),
        provenance=PROVENANCE,
        requested_quantity=1,
    )
    return replace(value, **changes)


def _input(**changes) -> RiskAssessmentInput:
    value = RiskAssessmentInput(
        input_id="input-1",
        snapshot_id="market-snapshot-1",
        strategy_decision=_strategy(),
        candidate=_candidate(),
        freshness_policy=_freshness(),
        evaluated_at=NOW,
        effective_session_id="session-1",
        latest_closed_at=NOW,
        account=_account(),
        positions=(_position(),),
        instrument=_instrument(),
        policy=_policy(),
    )
    return replace(value, **changes)


def _reasons(result) -> tuple[RiskReason, ...]:
    return (
        (result.primary_reason,) + result.contributing_reasons
        if result.primary_reason is not None
        else ()
    )


@pytest.mark.parametrize(
    ("disposition", "direction", "setup_ids", "reason_codes"),
    [
        (StrategyDisposition.NO_SIGNAL, StrategyDirection.FLAT, (), ()),
        (
            StrategyDisposition.REJECTED,
            StrategyDirection.FLAT,
            ("setup-1",),
            ("rejected",),
        ),
    ],
)
def test_non_candidate_is_not_applicable(
    disposition, direction, setup_ids, reason_codes
):
    strategy = _strategy(
        disposition=disposition,
        direction=direction,
        setup_ids=setup_ids,
        reason_codes=reason_codes,
    )

    result = assess_candidate_risk(_input(strategy_decision=strategy))

    assert result.status == AssessmentStatus.NOT_APPLICABLE
    assert result.primary_reason == RiskReason.CANDIDATE_NOT_APPLICABLE
    assert result.approved_quantity is None


def test_current_fixed_candidate_is_approved_with_integer_tick_math():
    result = assess_candidate_risk(_input())

    assert result.status == AssessmentStatus.APPROVED
    assert result.risk_ticks == 40
    assert result.risk_points == Decimal("10.00")
    assert result.risk_per_contract == Decimal("20.00")
    assert result.maximum_approved_quantity == 5
    assert result.approved_quantity == 1
    assert result.total_candidate_risk == Decimal("20.00")


@pytest.mark.parametrize(
    ("age", "expected_status", "expected_reason"),
    [
        (timedelta(seconds=31), FreshnessStatus.STALE, RiskReason.ACCOUNT_STALE),
        (
            timedelta(seconds=-3),
            FreshnessStatus.INVALID,
            RiskReason.ACCOUNT_INVALID,
        ),
    ],
)
def test_account_freshness_is_deterministic(age, expected_status, expected_reason):
    account = _account(observed_at=NOW - age, received_at=NOW - age)

    result = assess_candidate_risk(_input(account=account))

    assert result.status == AssessmentStatus.UNASSESSABLE
    assert result.account_freshness == expected_status
    assert expected_reason in _reasons(result)


def test_delayed_but_not_stale_snapshot_remains_assessable():
    account = _account(observed_at=NOW - timedelta(seconds=10), received_at=NOW)

    result = assess_candidate_risk(_input(account=account))

    assert result.status == AssessmentStatus.APPROVED
    assert result.account_freshness == FreshnessStatus.DELAYED


def test_stale_candidate_and_position_are_unassessable():
    occurred_at = NOW - timedelta(seconds=31)
    candidate = _candidate(candidate_at=occurred_at)
    strategy = _strategy(occurred_at=occurred_at)
    position = _position(observed_at=occurred_at, received_at=occurred_at)

    result = assess_candidate_risk(
        _input(
            strategy_decision=strategy,
            candidate=candidate,
            latest_closed_at=occurred_at,
            positions=(position,),
        )
    )

    assert result.status == AssessmentStatus.UNASSESSABLE
    assert result.position_freshness == FreshnessStatus.STALE
    assert result.candidate_freshness == FreshnessStatus.STALE
    assert RiskReason.POSITION_STALE in _reasons(result)
    assert RiskReason.CANDIDATE_EXPIRED in _reasons(result)


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"account": None}, RiskReason.ACCOUNT_MISSING),
        ({"positions": ()}, RiskReason.POSITION_MISSING),
        ({"instrument": None}, RiskReason.INSTRUMENT_MISSING),
        ({"policy": None}, RiskReason.POLICY_MISSING),
    ],
)
def test_missing_required_dependency_is_unassessable(changes, reason):
    result = assess_candidate_risk(_input(**changes))

    assert result.status == AssessmentStatus.UNASSESSABLE
    assert reason in _reasons(result)


def test_unreconciled_position_is_unassessable_and_never_assumed_flat():
    position = _position(reconciliation_status=ReconciliationStatus.UNRECONCILED)

    result = assess_candidate_risk(_input(positions=(position,)))

    assert result.status == AssessmentStatus.UNASSESSABLE
    assert RiskReason.POSITION_UNRECONCILED in _reasons(result)


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        (
            {"candidate": _candidate(strategy_version="2.0.0")},
            RiskReason.IDENTITY_MISMATCH,
        ),
        (
            {"latest_closed_at": NOW - timedelta(minutes=5)},
            RiskReason.TIMESTAMP_MISMATCH,
        ),
        (
            {"account": _account(effective_session_id="session-2")},
            RiskReason.SESSION_MISMATCH,
        ),
    ],
)
def test_alignment_failures_are_unassessable(change, reason):
    result = assess_candidate_risk(_input(**change))

    assert result.status == AssessmentStatus.UNASSESSABLE
    assert reason in _reasons(result)


@pytest.mark.parametrize(
    ("candidate", "reason"),
    [
        (
            _candidate(stop=Price(20_000, 0.25)),
            RiskReason.CANDIDATE_ZERO_STOP_DISTANCE,
        ),
        (
            _candidate(stop=Price(20_010, 0.25)),
            RiskReason.CANDIDATE_INVALID_STOP_GEOMETRY,
        ),
        (
            _candidate(
                entry=Price(20_000.1, 0.1),
                stop=Price(19_990.1, 0.1),
            ),
            RiskReason.CANDIDATE_LEVEL_MISMATCH,
        ),
    ],
)
def test_invalid_stop_or_tick_geometry_is_unassessable(candidate, reason):
    result = assess_candidate_risk(_input(candidate=candidate))

    assert result.status == AssessmentStatus.UNASSESSABLE
    assert reason in _reasons(result)


def test_fixed_quantity_above_policy_cap_is_blocked_without_rewrite():
    result = assess_candidate_risk(_input(candidate=_candidate(requested_quantity=12)))

    assert result.status == AssessmentStatus.BLOCKED
    assert result.requested_quantity == 12
    assert result.maximum_approved_quantity == 5
    assert result.approved_quantity == 0
    assert RiskReason.MAXIMUM_QUANTITY_EXCEEDED in _reasons(result)


def test_risk_based_sizing_floors_and_applies_quantity_increment():
    policy = _policy(
        sizing_mode=SizingMode.RISK_BASED,
        maximum_quantity=20,
        maximum_open_position_quantity=20,
        maximum_risk_per_trade=Decimal("115"),
    )
    instrument = _instrument(quantity_increment=2)

    result = assess_candidate_risk(_input(policy=policy, instrument=instrument))

    assert result.status == AssessmentStatus.APPROVED
    assert result.maximum_approved_quantity == 4
    assert result.approved_quantity == 4
    assert result.total_candidate_risk == Decimal("80.00")


def test_required_target_missing_is_unassessable():
    result = assess_candidate_risk(_input(policy=_policy(require_target=True)))

    assert result.status == AssessmentStatus.UNASSESSABLE
    assert RiskReason.CANDIDATE_TARGET_MISSING in _reasons(result)


def test_enforced_insufficient_margin_blocks_without_a_margin_engine():
    account = _account(available_margin=Decimal("50"))
    instrument = _instrument(margin_per_contract=Decimal("100"))
    policy = _policy(enforce_margin=True)

    result = assess_candidate_risk(
        _input(account=account, instrument=instrument, policy=policy)
    )

    assert result.status == AssessmentStatus.BLOCKED
    assert RiskReason.MARGIN_INSUFFICIENT in _reasons(result)
    assert result.approved_quantity == 0


@pytest.mark.parametrize(
    ("position", "reason"),
    [
        (
            _position(
                side=PositionSide.LONG,
                net_quantity=1,
                average_entry_price=Price(19_900, 0.25),
            ),
            RiskReason.MAXIMUM_EXPOSURE_EXCEEDED,
        ),
        (
            _position(
                side=PositionSide.SHORT,
                net_quantity=1,
                average_entry_price=Price(20_100, 0.25),
            ),
            RiskReason.OPPOSITE_POSITION,
        ),
        (
            _position(working_entry_quantity=5),
            RiskReason.WORKING_ORDER_LIMIT,
        ),
    ],
)
def test_v1_exposure_rules_block_candidate(position, reason):
    result = assess_candidate_risk(_input(positions=(position,)))

    assert result.status == AssessmentStatus.BLOCKED
    assert reason in _reasons(result)


@pytest.mark.parametrize(
    ("account", "reason"),
    [
        (
            _account(kill_switch_status=KillSwitchStatus.ACTIVE),
            RiskReason.ACCOUNT_KILL_SWITCH_ACTIVE,
        ),
        (
            _account(daily_realized_pnl=Decimal("-1000")),
            RiskReason.DAILY_LOSS_BREACHED,
        ),
        (
            _account(
                net_liquidation=Decimal("47999"),
                high_water_mark=Decimal("50000"),
            ),
            RiskReason.TRAILING_DRAWDOWN_BREACHED,
        ),
    ],
)
def test_account_policy_breaches_block(account, reason):
    result = assess_candidate_risk(_input(account=account))

    assert result.status == AssessmentStatus.BLOCKED
    assert reason in _reasons(result)


def test_reason_order_is_stable_and_primary_is_highest_precedence():
    candidate = _candidate(
        strategy_version="wrong",
        candidate_at=NOW - timedelta(minutes=1),
    )
    account = _account(
        observed_at=NOW - timedelta(minutes=1),
        received_at=NOW - timedelta(minutes=1),
        reconciliation_status=ReconciliationStatus.UNRECONCILED,
    )

    result = assess_candidate_risk(
        _input(candidate=candidate, account=account, positions=())
    )

    assert result.status == AssessmentStatus.UNASSESSABLE
    assert _reasons(result) == (
        RiskReason.IDENTITY_MISMATCH,
        RiskReason.TIMESTAMP_MISMATCH,
        RiskReason.ACCOUNT_STALE,
        RiskReason.ACCOUNT_UNRECONCILED,
        RiskReason.POSITION_MISSING,
        RiskReason.CANDIDATE_EXPIRED,
    )


def test_assessment_is_repeatable_and_does_not_mutate_input():
    input_value = _input()
    before = hash(input_value)

    first = assess_candidate_risk(input_value)
    second = assess_candidate_risk(input_value)

    assert first == second
    assert hash(input_value) == before
    assert first.identity.assessment_id == second.identity.assessment_id
