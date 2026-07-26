"""Deterministic fail-closed alignment into existing RiskAssessment contracts."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from atlas.risk_assessment.models import (
    CandidateTradeInput,
    RiskAssessmentInput,
    RiskPolicy,
    SizingMode,
)
from atlas.strategy_engine.models import StrategyDecision, StrategyDisposition

from .models import (
    AlignmentReason,
    AlignmentResult,
    ProposedTrade,
    QuantityResolution,
    SourceAuthority,
    StrategyCandidateIdentity,
)


def validate_proposal(
    *,
    strategy: StrategyDecision,
    proposal: ProposedTrade,
    policy: RiskPolicy | None,
    evaluated_at: datetime,
    maximum_age_seconds: Decimal,
) -> AlignmentResult:
    reasons: list[AlignmentReason] = []
    if strategy.disposition != StrategyDisposition.CANDIDATE:
        reasons.append(AlignmentReason.STRATEGY_NOT_CANDIDATE)
    else:
        if StrategyCandidateIdentity.from_decision(strategy) != proposal.candidate:
            reasons.append(AlignmentReason.CANDIDATE_IDENTITY_MISMATCH)
    if strategy.occurred_at != proposal.candidate.occurred_at:
        reasons.append(AlignmentReason.CANDIDATE_TIMESTAMP_MISMATCH)
    if strategy.direction != proposal.direction:
        reasons.append(AlignmentReason.CANDIDATE_DIRECTION_MISMATCH)
    if (
        proposal.analysis_series.economic_instrument
        != proposal.economic_instrument
        or proposal.listed_instrument.economic_instrument
        != proposal.economic_instrument
    ):
        reasons.append(AlignmentReason.ECONOMIC_INSTRUMENT_MISMATCH)
    if (
        proposal.analysis_series.series_type.value == "continuous"
        and proposal.analysis_series.symbol
        == proposal.listed_instrument.contract_symbol
    ):
        reasons.append(AlignmentReason.CONTINUOUS_SERIES_AS_CONTRACT)
    if policy is not None and policy.require_target and proposal.target is None:
        reasons.append(AlignmentReason.TARGET_REQUIRED)
    if (
        proposal.quantity_resolution == QuantityResolution.UNRESOLVED
        and (policy is None or policy.sizing_mode != SizingMode.RISK_BASED)
    ):
        reasons.append(AlignmentReason.QUANTITY_UNRESOLVED)
    if proposal.created_at > evaluated_at:
        reasons.append(AlignmentReason.PROPOSAL_FUTURE)
    elif Decimal(str((evaluated_at - proposal.created_at).total_seconds())) > maximum_age_seconds:
        reasons.append(AlignmentReason.PROPOSAL_STALE)
    if proposal.authority.authority != SourceAuthority.AUTHORITATIVE:
        reasons.append(AlignmentReason.SOURCE_NOT_AUTHORITATIVE)
    if not proposal.authority.reconciled:
        reasons.append(AlignmentReason.SOURCE_UNRECONCILED)
    return AlignmentResult(tuple(dict.fromkeys(reasons)))


def to_candidate_trade_input(proposal: ProposedTrade) -> CandidateTradeInput:
    """Lossless adapter to the existing formal RiskAssessment candidate."""
    return CandidateTradeInput(
        candidate_id=proposal.proposal_id,
        strategy_id=proposal.candidate.strategy_id,
        strategy_version=proposal.candidate.strategy_version,
        context_fingerprint=proposal.candidate.context_fingerprint,
        product=proposal.economic_instrument.symbol,
        contract_symbol=proposal.listed_instrument.contract_symbol,
        candidate_at=proposal.candidate.occurred_at,
        direction=proposal.direction.value,
        entry_type=proposal.entry_type,
        entry=proposal.entry,
        stop=proposal.stop,
        target=proposal.target,
        invalidation=proposal.invalidation,
        requested_quantity=proposal.requested_quantity,
        provenance=proposal.authority.provenance,
    )


def validate_risk_input_alignment(
    proposal: ProposedTrade, risk_input: RiskAssessmentInput
) -> AlignmentResult:
    expected = to_candidate_trade_input(proposal)
    reasons: list[AlignmentReason] = []
    if (
        risk_input.strategy_decision.disposition != StrategyDisposition.CANDIDATE
        or StrategyCandidateIdentity.from_decision(risk_input.strategy_decision)
        != proposal.candidate
    ):
        reasons.append(AlignmentReason.RISK_INPUT_MISMATCH)
    if risk_input.candidate != expected:
        reasons.append(AlignmentReason.RISK_INPUT_MISMATCH)
    if (
        risk_input.instrument is not None
        and (
            risk_input.instrument.product != proposal.economic_instrument.symbol
            or risk_input.instrument.contract_symbol
            != proposal.listed_instrument.contract_symbol
        )
    ):
        reasons.append(AlignmentReason.LISTED_INSTRUMENT_MISMATCH)
    if any(
        position.product != proposal.economic_instrument.symbol
        or position.contract_symbol != proposal.listed_instrument.contract_symbol
        for position in risk_input.positions
    ):
        reasons.append(AlignmentReason.LISTED_INSTRUMENT_MISMATCH)
    return AlignmentResult(tuple(dict.fromkeys(reasons)))
