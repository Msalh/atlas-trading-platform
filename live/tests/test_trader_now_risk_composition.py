"""Part 9G read-only TraderNow risk composition certification."""

from dataclasses import replace
from decimal import Decimal
import importlib

import pytest

from atlas.core.primitives import Price
from atlas.risk_assessment.models import AssessmentStatus, RiskReason
from atlas.risk_assessment.service import assess_candidate_risk
from atlas.risk_projection import project_risk_assessment
from atlas.strategy_engine.models import StrategyDirection, StrategyDisposition
from atlas.trader_now.errors import RiskCompositionAlignmentError
from atlas.trader_now.models import (
    Availability,
    AvailabilityStatus,
    DecisionNotImplemented,
    TraderNow,
    TraderNowIdentity,
    Trust,
    TrustStatus,
)
from atlas.trader_now.service import TraderNowService
from tests.risk_assessment_fixtures import (
    account_snapshot,
    assessment_input,
    candidate_trade_input,
    strategy_decision,
)


def trader_now_result() -> TraderNow:
    return TraderNow(
        snapshot=None,
        identity=TraderNowIdentity(
            product="MNQ",
            symbol="MNQ",
            timeframe="5m",
            strategy_id="displacement_volume_context",
            strategy_version="1.0.0",
        ),
        trust=Trust(
            TrustStatus.TRUSTED,
            "freshness.v1",
        ),
        availability={"market": Availability(AvailabilityStatus.AVAILABLE)},
        decision=DecisionNotImplemented(),
    )


def compose(input_value):
    return TraderNowService().compose_risk(
        trader_now_result(),
        strategy_decisions=(input_value.strategy_decision,),
        risk_input=input_value,
    )


def test_absent_risk_input_preserves_existing_result_by_identity():
    result = trader_now_result()

    composed = TraderNowService().compose_risk(result)

    assert composed is result
    assert composed.risk is None


@pytest.mark.parametrize(
    ("input_value", "expected_status"),
    [
        (assessment_input(), AssessmentStatus.APPROVED),
        (
            assessment_input(
                account=account_snapshot(daily_realized_pnl=Decimal("-1000"))
            ),
            AssessmentStatus.BLOCKED,
        ),
        (
            assessment_input(
                candidate=candidate_trade_input(
                    entry=Price(20_000.1, 0.1),
                    stop=Price(19_990.1, 0.1),
                )
            ),
            AssessmentStatus.UNASSESSABLE,
        ),
        (
            assessment_input(
                strategy_decision=strategy_decision(
                    disposition=StrategyDisposition.NO_SIGNAL,
                    direction=StrategyDirection.FLAT,
                    setup_ids=(),
                )
            ),
            AssessmentStatus.NOT_APPLICABLE,
        ),
    ],
)
def test_canonical_status_projection_is_attached_exactly(input_value, expected_status):
    expected = project_risk_assessment(assess_candidate_risk(input_value))

    result = compose(input_value)

    assert result.risk == expected
    assert result.risk is not None
    assert result.risk.status is expected_status


def test_composition_calls_both_canonical_functions(monkeypatch):
    service_module = importlib.import_module("atlas.trader_now.service")
    risk_input = assessment_input()
    calls = {"assess": 0, "project": 0}

    def tracking_assess(value):
        calls["assess"] += 1
        return assess_candidate_risk(value)

    def tracking_project(value):
        calls["project"] += 1
        return project_risk_assessment(value)

    monkeypatch.setattr(service_module, "assess_candidate_risk", tracking_assess)
    monkeypatch.setattr(service_module, "project_risk_assessment", tracking_project)

    compose(risk_input)

    assert calls == {"assess": 1, "project": 1}


def test_repeated_composition_is_deterministic_and_mutates_nothing():
    input_value = assessment_input()
    source = trader_now_result()
    input_hash = hash(input_value)

    first = TraderNowService().compose_risk(
        source,
        strategy_decisions=(input_value.strategy_decision,),
        risk_input=input_value,
    )
    second = TraderNowService().compose_risk(
        source,
        strategy_decisions=(input_value.strategy_decision,),
        risk_input=input_value,
    )

    assert first == second
    assert first is not source
    assert source.risk is None
    assert hash(input_value) == input_hash
    assert first.risk is not None
    assert hash(first.risk) == hash(second.risk)


def test_identity_policy_reasons_and_all_values_are_preserved_exactly():
    input_value = assessment_input(
        account=account_snapshot(daily_realized_pnl=Decimal("-1000"))
    )
    expected = project_risk_assessment(assess_candidate_risk(input_value))

    projection = compose(input_value).risk

    assert projection == expected
    assert projection is not None
    assert projection.assessment_id == expected.assessment_id
    assert projection.policy_id == expected.policy_id
    assert projection.policy_version == expected.policy_version
    assert projection.primary_reason is RiskReason.DAILY_LOSS_BREACHED
    assert projection.contributing_reasons == expected.contributing_reasons
    assert projection.requested_quantity == expected.requested_quantity
    assert projection.maximum_approved_quantity == expected.maximum_approved_quantity
    assert projection.approved_quantity == expected.approved_quantity
    assert projection.risk_dollars_per_contract == expected.risk_dollars_per_contract
    assert projection.account_freshness is expected.account_freshness
    assert projection.position_freshness is expected.position_freshness
    assert projection.candidate_freshness is expected.candidate_freshness
    assert projection.reconciliation_status is expected.reconciliation_status
    assert projection.source_summary == expected.source_summary


def test_correlation_matches_by_value_not_tuple_order():
    input_value = assessment_input()
    unrelated = replace(
        input_value.strategy_decision,
        context_fingerprint="unrelated-context",
    )

    result = TraderNowService().compose_risk(
        trader_now_result(),
        strategy_decisions=(unrelated, input_value.strategy_decision),
        risk_input=input_value,
    )

    assert result.risk is not None


@pytest.mark.parametrize("decisions", [(), None])
def test_missing_canonical_strategy_match_is_rejected(decisions):
    input_value = assessment_input()
    supplied = (
        (replace(input_value.strategy_decision, context_fingerprint="other"),)
        if decisions is None
        else decisions
    )

    with pytest.raises(RiskCompositionAlignmentError, match="exactly one") as exc:
        TraderNowService().compose_risk(
            trader_now_result(),
            strategy_decisions=supplied,
            risk_input=input_value,
        )

    assert exc.value.match_count == 0


def test_duplicate_canonical_strategy_matches_are_rejected():
    input_value = assessment_input()

    with pytest.raises(RiskCompositionAlignmentError) as exc:
        TraderNowService().compose_risk(
            trader_now_result(),
            strategy_decisions=(
                input_value.strategy_decision,
                input_value.strategy_decision,
            ),
            risk_input=input_value,
        )

    assert exc.value.match_count == 2
