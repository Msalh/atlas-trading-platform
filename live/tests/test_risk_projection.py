"""Structural and behavioral certification for the risk projection."""

from dataclasses import FrozenInstanceError, fields, replace
from decimal import Decimal

import pytest

from atlas.core.primitives import Price
from atlas.risk_assessment.models import (
    AssessmentStatus,
    FreshnessStatus,
    RiskReason,
)
from atlas.risk_assessment.service import assess_candidate_risk
from atlas.risk_projection import (
    RISK_PROJECTION_SCHEMA_VERSION,
    RiskProjection,
    project_risk_assessment,
)
from atlas.strategy_engine.models import StrategyDirection, StrategyDisposition
from tests.risk_assessment_fixtures import (
    account_snapshot,
    assessment_input,
    candidate_trade_input,
    strategy_decision,
)

EXPECTED_FIELDS = (
    "schema_version",
    "assessment_id",
    "policy_id",
    "policy_version",
    "assessed_at",
    "candidate_at",
    "status",
    "primary_reason",
    "contributing_reasons",
    "sizing_mode",
    "requested_quantity",
    "maximum_approved_quantity",
    "approved_quantity",
    "risk_ticks",
    "risk_dollars_per_contract",
    "approved_total_candidate_risk",
    "remaining_daily_risk_capacity",
    "remaining_drawdown_capacity",
    "exposure_before",
    "exposure_after",
    "account_freshness",
    "position_freshness",
    "candidate_freshness",
    "reconciliation_status",
    "has_delayed_data",
    "source_summary",
)


def test_projection_has_exact_approved_surface_and_field_mapping():
    assessment = assess_candidate_risk(assessment_input())

    projection = project_risk_assessment(assessment)

    assert tuple(field.name for field in fields(RiskProjection)) == EXPECTED_FIELDS
    assert projection == RiskProjection(
        schema_version=RISK_PROJECTION_SCHEMA_VERSION,
        assessment_id=assessment.identity.assessment_id,
        policy_id=assessment.identity.policy_id,
        policy_version=assessment.identity.policy_version,
        assessed_at=assessment.assessed_at,
        candidate_at=assessment.candidate_at,
        status=assessment.status,
        primary_reason=assessment.primary_reason,
        contributing_reasons=assessment.contributing_reasons,
        sizing_mode=assessment.sizing_mode,
        requested_quantity=assessment.requested_quantity,
        maximum_approved_quantity=assessment.maximum_approved_quantity,
        approved_quantity=assessment.approved_quantity,
        risk_ticks=assessment.risk_ticks,
        risk_dollars_per_contract=assessment.risk_per_contract,
        approved_total_candidate_risk=assessment.total_candidate_risk,
        remaining_daily_risk_capacity=assessment.remaining_daily_risk,
        remaining_drawdown_capacity=assessment.remaining_drawdown,
        exposure_before=assessment.exposure_before,
        exposure_after=assessment.exposure_after,
        account_freshness=assessment.account_freshness,
        position_freshness=assessment.position_freshness,
        candidate_freshness=assessment.candidate_freshness,
        reconciliation_status=assessment.reconciliation_status,
        has_delayed_data=False,
        source_summary=assessment.source_identities,
    )


def test_reason_order_quantities_money_freshness_and_sources_are_preserved():
    base = assess_candidate_risk(assessment_input())
    assessment = replace(
        base,
        status=AssessmentStatus.BLOCKED,
        primary_reason=RiskReason.ACCOUNT_STALE,
        contributing_reasons=(
            RiskReason.POSITION_STALE,
            RiskReason.CANDIDATE_EXPIRED,
        ),
        requested_quantity=4,
        maximum_approved_quantity=2,
        approved_quantity=0,
        risk_ticks=17,
        risk_per_contract=Decimal("8.50"),
        total_candidate_risk=Decimal("0"),
        remaining_daily_risk=Decimal("125.25"),
        remaining_drawdown=Decimal("900.75"),
        account_freshness=FreshnessStatus.DELAYED,
        position_freshness=FreshnessStatus.CURRENT,
        candidate_freshness=FreshnessStatus.STALE,
        source_identities=("account:1", "candidate:1"),
    )

    projection = project_risk_assessment(assessment)

    assert projection.primary_reason is RiskReason.ACCOUNT_STALE
    assert projection.contributing_reasons == (
        RiskReason.POSITION_STALE,
        RiskReason.CANDIDATE_EXPIRED,
    )
    assert (
        projection.requested_quantity,
        projection.maximum_approved_quantity,
        projection.approved_quantity,
    ) == (4, 2, 0)
    assert projection.risk_ticks == 17
    assert projection.risk_dollars_per_contract == Decimal("8.50")
    assert projection.approved_total_candidate_risk == Decimal("0")
    assert projection.remaining_daily_risk_capacity == Decimal("125.25")
    assert projection.remaining_drawdown_capacity == Decimal("900.75")
    assert projection.account_freshness is FreshnessStatus.DELAYED
    assert projection.position_freshness is FreshnessStatus.CURRENT
    assert projection.candidate_freshness is FreshnessStatus.STALE
    assert projection.has_delayed_data is True
    assert projection.source_summary == ("account:1", "candidate:1")


def test_none_values_are_not_replaced_with_defaults():
    assessment = assess_candidate_risk(
        assessment_input(
            account=None,
            instrument=None,
            policy=None,
            positions=(),
        )
    )

    projection = project_risk_assessment(assessment)

    assert projection.policy_id is None
    assert projection.policy_version is None
    assert projection.sizing_mode is None
    assert projection.maximum_approved_quantity is None
    assert projection.approved_quantity is None
    assert projection.risk_ticks is None
    assert projection.risk_dollars_per_contract is None
    assert projection.approved_total_candidate_risk is None
    assert projection.remaining_daily_risk_capacity is None
    assert projection.remaining_drawdown_capacity is None
    assert projection.reconciliation_status is None


def test_projection_is_immutable_hashable_repeatable_and_does_not_mutate_source():
    assessment = assess_candidate_risk(assessment_input())
    original_hash = hash(assessment)

    first = project_risk_assessment(assessment)
    second = project_risk_assessment(assessment)

    assert first == second
    assert hash(first) == hash(second)
    assert hash(assessment) == original_hash
    with pytest.raises(FrozenInstanceError):
        first.status = AssessmentStatus.BLOCKED  # type: ignore[misc]


@pytest.mark.parametrize("status", tuple(AssessmentStatus))
def test_every_assessment_status_projects_without_special_case_failure(status):
    assessment = replace(
        assess_candidate_risk(assessment_input()),
        status=status,
    )

    assert project_risk_assessment(assessment).status is status


@pytest.mark.parametrize(
    "assessment",
    [
        assess_candidate_risk(assessment_input()),
        assess_candidate_risk(
            assessment_input(
                account=account_snapshot(daily_realized_pnl=Decimal("-1000"))
            )
        ),
        assess_candidate_risk(
            assessment_input(
                candidate=candidate_trade_input(
                    entry=Price(20_000.1, 0.1),
                    stop=Price(19_990.1, 0.1),
                ),
            )
        ),
        assess_candidate_risk(
            assessment_input(
                strategy_decision=strategy_decision(
                    disposition=StrategyDisposition.NO_SIGNAL,
                    direction=StrategyDirection.FLAT,
                    setup_ids=(),
                ),
            )
        ),
    ],
)
def test_representative_status_results_project_without_reinterpretation(assessment):
    projection = project_risk_assessment(assessment)

    assert projection.status is assessment.status
    assert projection.primary_reason is assessment.primary_reason
    assert projection.contributing_reasons == assessment.contributing_reasons
