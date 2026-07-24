"""Immutable read-only projection contract for RiskAssessment results."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from atlas.risk_assessment.models import (
    AssessmentStatus,
    FreshnessStatus,
    ReconciliationStatus,
    RiskReason,
    SizingMode,
)

RISK_PROJECTION_SCHEMA_VERSION = "risk_projection.v1"


@dataclass(frozen=True)
class RiskProjection:
    schema_version: str
    assessment_id: str
    policy_id: str | None
    policy_version: str | None
    assessed_at: datetime
    candidate_at: datetime
    status: AssessmentStatus
    primary_reason: RiskReason | None
    contributing_reasons: tuple[RiskReason, ...]
    sizing_mode: SizingMode | None
    requested_quantity: int | None
    maximum_approved_quantity: int | None
    approved_quantity: int | None
    risk_ticks: int | None
    risk_dollars_per_contract: Decimal | None
    approved_total_candidate_risk: Decimal | None
    remaining_daily_risk_capacity: Decimal | None
    remaining_drawdown_capacity: Decimal | None
    exposure_before: int | None
    exposure_after: int | None
    account_freshness: FreshnessStatus
    position_freshness: FreshnessStatus
    candidate_freshness: FreshnessStatus
    reconciliation_status: ReconciliationStatus | None
    has_delayed_data: bool
    source_summary: tuple[str, ...]
