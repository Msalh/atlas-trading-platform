"""Replay/live equivalence and V1 RiskAssessment certification."""

from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from decimal import Decimal

import pytest

from atlas.core.primitives import Price
from atlas.risk_assessment.models import (
    AssessmentStatus,
    KillSwitchStatus,
    PositionSide,
    RiskReason,
    SizingMode,
)
from atlas.risk_assessment.service import assess_candidate_risk
from tests.risk_assessment_fixtures import (
    EVALUATED_AT,
    account_snapshot,
    assessment_input,
    candidate_trade_input,
    equivalent_input_pair,
    fixture_set,
    instrument_specification,
    position_snapshot,
    risk_policy,
)


def reasons(result) -> tuple[RiskReason, ...]:
    if result.primary_reason is None:
        return ()
    return (result.primary_reason,) + result.contributing_reasons


def assert_business_equivalent(replay_result, live_result) -> None:
    assert replay_result.status == live_result.status
    assert replay_result.approved_quantity == live_result.approved_quantity
    assert (
        replay_result.maximum_approved_quantity == live_result.maximum_approved_quantity
    )
    assert replay_result.requested_quantity == live_result.requested_quantity
    assert replay_result.risk_per_contract == live_result.risk_per_contract
    assert replay_result.total_candidate_risk == live_result.total_candidate_risk
    assert replay_result.risk_ticks == live_result.risk_ticks
    assert replay_result.exposure_before == live_result.exposure_before
    assert replay_result.exposure_after == live_result.exposure_after
    assert replay_result.primary_reason == live_result.primary_reason
    assert replay_result.contributing_reasons == live_result.contributing_reasons
    assert replay_result.sizing_mode == live_result.sizing_mode
    assert replay_result.identity == live_result.identity
    assert replay_result.account_freshness == live_result.account_freshness
    assert replay_result.position_freshness == live_result.position_freshness
    assert replay_result.candidate_freshness == live_result.candidate_freshness
    assert replay_result.reconciliation_status == live_result.reconciliation_status


def test_replay_and_live_shaped_inputs_differ_only_in_provenance():
    replay = fixture_set("replay")
    live = fixture_set("live")

    assert replay.account == replace(live.account, provenance=replay.account.provenance)
    assert replay.position == replace(
        live.position, provenance=replay.position.provenance
    )
    assert replay.instrument == replace(
        live.instrument, provenance=replay.instrument.provenance
    )
    assert replay.freshness_policy == replace(
        live.freshness_policy, provenance=replay.freshness_policy.provenance
    )
    assert replay.risk_policy == replace(
        live.risk_policy, provenance=replay.risk_policy.provenance
    )
    assert replay.candidate == replace(
        live.candidate, provenance=replay.candidate.provenance
    )
    assert replay.strategy_decision == live.strategy_decision


def test_replay_and_live_assessments_are_business_equivalent():
    replay_input, live_input = equivalent_input_pair()

    replay_result = assess_candidate_risk(replay_input)
    live_result = assess_candidate_risk(live_input)

    assert_business_equivalent(replay_result, live_result)
    assert replay_result.source_identities != live_result.source_identities
    assert set(replay_result.source_identities) ^ set(
        live_result.source_identities
    ) == {
        "replay:candidate",
        "live:candidate",
    }


@pytest.mark.parametrize(
    ("name", "changed_input", "expected_change"),
    [
        (
            "policy",
            assessment_input(
                policy=risk_policy(
                    policy_version="2.0.0",
                    maximum_quantity=0,
                    maximum_open_position_quantity=0,
                )
            ),
            "status",
        ),
        (
            "instrument",
            assessment_input(
                instrument=instrument_specification(maximum_platform_quantity=1)
            ),
            "maximum_quantity",
        ),
        (
            "tick_value",
            assessment_input(
                instrument=instrument_specification(tick_value=Decimal("1.00"))
            ),
            "risk",
        ),
        (
            "entry",
            assessment_input(
                candidate=candidate_trade_input(entry=Price(20_005, 0.25))
            ),
            "ticks",
        ),
        (
            "stop",
            assessment_input(candidate=candidate_trade_input(stop=Price(19_995, 0.25))),
            "ticks",
        ),
        (
            "account_equity",
            assessment_input(
                account=account_snapshot(
                    net_liquidation=Decimal("100"),
                    high_water_mark=Decimal("100"),
                ),
                policy=risk_policy(
                    sizing_mode=SizingMode.RISK_BASED,
                    maximum_quantity=20,
                    maximum_open_position_quantity=20,
                    maximum_risk_per_trade=None,
                    maximum_risk_fraction=Decimal("0.01"),
                    trailing_drawdown_limit=None,
                ),
            ),
            "status",
        ),
        (
            "drawdown",
            assessment_input(
                account=account_snapshot(
                    net_liquidation=Decimal("47999"),
                    high_water_mark=Decimal("50000"),
                )
            ),
            "status",
        ),
        (
            "working_orders",
            assessment_input(positions=(position_snapshot(working_entry_quantity=4),)),
            "maximum_quantity",
        ),
        (
            "position",
            assessment_input(
                positions=(
                    position_snapshot(
                        side=PositionSide.LONG,
                        net_quantity=1,
                        average_entry_price=Price(19_900, 0.25),
                    ),
                )
            ),
            "status",
        ),
        (
            "freshness",
            assessment_input(
                account=account_snapshot(
                    observed_at=EVALUATED_AT - timedelta(seconds=31),
                    received_at=EVALUATED_AT - timedelta(seconds=31),
                )
            ),
            "status",
        ),
        (
            "session",
            assessment_input(
                account=account_snapshot(effective_session_id="session-2"),
                effective_session_id="session-2",
            ),
            "status",
        ),
    ],
)
def test_business_input_changes_have_deterministic_explainable_effects(
    name, changed_input, expected_change
):
    baseline = assess_candidate_risk(assessment_input())
    changed = assess_candidate_risk(changed_input)

    observations = {
        "status": baseline.status != changed.status,
        "maximum_quantity": (
            baseline.maximum_approved_quantity != changed.maximum_approved_quantity
        ),
        "risk": baseline.risk_per_contract != changed.risk_per_contract,
        "ticks": baseline.risk_ticks != changed.risk_ticks,
    }
    assert observations[expected_change], name


def test_identical_input_produces_identical_immutable_output_without_mutation():
    value = assessment_input()
    original_hash = hash(value)

    first = assess_candidate_risk(value)
    second = assess_candidate_risk(value)

    assert first == second
    assert hash(first) == hash(second)
    assert hash(value) == original_hash
    with pytest.raises(FrozenInstanceError):
        first.status = AssessmentStatus.BLOCKED  # type: ignore[misc]


def test_assessment_identity_is_stable_and_provenance_independent():
    replay_input, live_input = equivalent_input_pair()

    replay_identity = assess_candidate_risk(replay_input).identity
    live_identity = assess_candidate_risk(live_input).identity

    assert replay_identity == live_identity
    assert replay_identity.assessment_id == ("risk:risk-input-1:candidate-1:1.0.0")


@pytest.mark.parametrize(
    ("input_value", "status", "primary", "approved", "maximum"),
    [
        (
            assessment_input(),
            AssessmentStatus.APPROVED,
            None,
            1,
            5,
        ),
        (
            assessment_input(policy=risk_policy(sizing_mode=SizingMode.RISK_BASED)),
            AssessmentStatus.APPROVED,
            None,
            5,
            5,
        ),
        (
            assessment_input(
                candidate=candidate_trade_input(
                    entry=Price(20_000.1, 0.1),
                    stop=Price(19_990.1, 0.1),
                )
            ),
            AssessmentStatus.UNASSESSABLE,
            RiskReason.CANDIDATE_LEVEL_MISMATCH,
            None,
            None,
        ),
        (
            assessment_input(
                account=account_snapshot(kill_switch_status=KillSwitchStatus.ACTIVE)
            ),
            AssessmentStatus.BLOCKED,
            RiskReason.ACCOUNT_KILL_SWITCH_ACTIVE,
            0,
            5,
        ),
        (
            assessment_input(
                account=account_snapshot(daily_realized_pnl=Decimal("-1000"))
            ),
            AssessmentStatus.BLOCKED,
            RiskReason.DAILY_LOSS_BREACHED,
            0,
            0,
        ),
        (
            assessment_input(
                account=account_snapshot(
                    net_liquidation=Decimal("47999"),
                    high_water_mark=Decimal("50000"),
                )
            ),
            AssessmentStatus.BLOCKED,
            RiskReason.TRAILING_DRAWDOWN_BREACHED,
            0,
            0,
        ),
        (
            assessment_input(positions=(position_snapshot(working_entry_quantity=5),)),
            AssessmentStatus.BLOCKED,
            RiskReason.WORKING_ORDER_LIMIT,
            0,
            0,
        ),
        (
            assessment_input(
                positions=(
                    position_snapshot(
                        side=PositionSide.LONG,
                        net_quantity=1,
                        average_entry_price=Price(19_900, 0.25),
                    ),
                )
            ),
            AssessmentStatus.BLOCKED,
            RiskReason.MAXIMUM_EXPOSURE_EXCEEDED,
            0,
            4,
        ),
        (
            assessment_input(
                positions=(
                    position_snapshot(
                        side=PositionSide.SHORT,
                        net_quantity=1,
                        average_entry_price=Price(20_100, 0.25),
                    ),
                ),
                policy=risk_policy(maximum_concurrent_positions=2),
            ),
            AssessmentStatus.BLOCKED,
            RiskReason.OPPOSITE_POSITION,
            0,
            4,
        ),
    ],
)
def test_v1_regression_matrix(input_value, status, primary, approved, maximum):
    result = assess_candidate_risk(input_value)

    assert result.status == status
    assert result.primary_reason == primary
    assert result.approved_quantity == approved
    assert result.maximum_approved_quantity == maximum


def test_tick_conversion_and_reason_order_are_frozen():
    account = account_snapshot(
        observed_at=EVALUATED_AT - timedelta(seconds=31),
        received_at=EVALUATED_AT - timedelta(seconds=31),
    )
    candidate = candidate_trade_input(
        strategy_version="wrong",
        candidate_at=EVALUATED_AT - timedelta(seconds=31),
    )
    result = assess_candidate_risk(
        assessment_input(
            account=account,
            positions=(),
            candidate=candidate,
        )
    )

    assert reasons(result) == (
        RiskReason.IDENTITY_MISMATCH,
        RiskReason.TIMESTAMP_MISMATCH,
        RiskReason.ACCOUNT_STALE,
        RiskReason.POSITION_MISSING,
        RiskReason.CANDIDATE_EXPIRED,
    )

    approved = assess_candidate_risk(assessment_input())
    assert approved.risk_ticks == 40
    assert approved.risk_points == Decimal("10.00")
    assert approved.risk_per_contract == Decimal("20.00")
