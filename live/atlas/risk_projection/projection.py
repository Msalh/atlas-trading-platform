"""Pure projection from the canonical RiskAssessment result."""

from atlas.risk_assessment.models import FreshnessStatus, RiskAssessment
from atlas.risk_projection.models import (
    RISK_PROJECTION_SCHEMA_VERSION,
    RiskProjection,
)


def project_risk_assessment(assessment: RiskAssessment) -> RiskProjection:
    """Copy approved read-only fields without re-evaluating risk."""
    freshness = (
        assessment.account_freshness,
        assessment.position_freshness,
        assessment.candidate_freshness,
    )
    return RiskProjection(
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
        has_delayed_data=FreshnessStatus.DELAYED in freshness,
        source_summary=assessment.source_identities,
    )
