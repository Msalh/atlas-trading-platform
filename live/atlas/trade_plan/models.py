"""Frozen pure-domain contracts for Product P2B-1 trade-plan geometry."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from atlas.risk_assessment.models import InstrumentSpecification
from atlas.strategy_engine.models import StrategyDecision
from atlas.trade_risk_authority.models import (
    AuthorityMetadata,
    ProposedTrade,
    StrategyCandidateIdentity,
)
from atlas.trader_now.models import (
    ListedInstrument,
    MarketInputIdentity,
    SourceEventIdentity,
)

TRADE_PLAN_INPUT_SCHEMA_VERSION = "trade_plan_input.v1"
TRADE_PLAN_POLICY_SCHEMA_VERSION = "trade_plan_policy.v1"
TRADE_PLAN_EVIDENCE_BINDING_SCHEMA_VERSION = "trade_plan_evidence_binding.v1"
TRADE_PLAN_RESULT_SCHEMA_VERSION = "trade_plan_result.v1"
TRADE_PLAN_REFUSAL_SCHEMA_VERSION = "trade_plan_refusal.v1"


def _text(name: str, value: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{name} must not be blank")


def _aware(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


class EvidenceAvailability(str, Enum):
    AVAILABLE = "available"
    INSUFFICIENT = "insufficient"
    UNAVAILABLE = "unavailable"
    CONFLICTING = "conflicting"


class TradePlanStatus(str, Enum):
    GENERATED = "generated"
    REFUSED = "refused"


class TradePlanPurpose(str, Enum):
    ANALYSIS_ONLY = "analysis_only"


class TradePlanAuthority(str, Enum):
    PROPOSED_GEOMETRY = "proposed_geometry"


class TradePlanRefusalReason(str, Enum):
    """The only P2B-1 refusal vocabulary; no competing reason contract exists."""

    RULES_UNAVAILABLE = "trade_plan.evidence.rules_unavailable"
    SETUPS_UNAVAILABLE = "trade_plan.evidence.setups_unavailable"
    INTERPRETATION_UNAVAILABLE = "trade_plan.evidence.interpretation_unavailable"
    CONTEXT_UNAVAILABLE = "trade_plan.evidence.context_unavailable"
    STRATEGY_NOT_CANDIDATE = "trade_plan.strategy.not_candidate"
    STRATEGY_GEOMETRY_CONFLICT = "trade_plan.strategy.geometry_authority_conflict"
    CANDIDATE_MISMATCH = "trade_plan.identity.candidate_mismatch"
    SOURCE_EVENT_MISMATCH = "trade_plan.identity.source_event_mismatch"
    SOURCE_NOT_AUTHORITATIVE = "trade_plan.evidence.not_authoritative"
    SOURCE_UNRECONCILED = "trade_plan.evidence.unreconciled"
    EVIDENCE_STALE = "trade_plan.evidence.stale"
    EVIDENCE_FUTURE = "trade_plan.evidence.future"
    CANDIDATE_BAR_INCOMPLETE = "trade_plan.evidence.candidate_bar_incomplete"
    CANDIDATE_BAR_INVALID = "trade_plan.evidence.candidate_bar_invalid"
    LISTED_INSTRUMENT_MISSING = "trade_plan.instrument.listed_missing"
    LISTED_INSTRUMENT_MISMATCH = "trade_plan.instrument.listed_mismatch"
    CONTINUOUS_SERIES_AS_CONTRACT = "trade_plan.instrument.continuous_as_listed"
    SPECIFICATION_MISSING = "trade_plan.instrument.specification_missing"
    SPECIFICATION_MISMATCH = "trade_plan.instrument.specification_mismatch"
    SPECIFICATION_NOT_AUTHORITATIVE = "trade_plan.instrument.specification_not_authoritative"
    POLICY_MISSING = "trade_plan.policy.missing"
    POLICY_NOT_AUTHORITATIVE = "trade_plan.policy.not_authoritative"
    EXPIRY_INVALID = "trade_plan.expiry.invalid"
    GEOMETRY_INVALID = "trade_plan.geometry.invalid"
    RISK_DISTANCE_TOO_SMALL = "trade_plan.geometry.risk_distance_too_small"
    ROUNDING_COLLAPSE = "trade_plan.geometry.rounding_collapse"


@dataclass(frozen=True)
class CandidateBarEvidence:
    source_event: SourceEventIdentity
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal

    def __post_init__(self) -> None:
        _aware("source_event.occurred_at", self.source_event.occurred_at)
        _aware("source_event.received_at", self.source_event.received_at)
        if self.source_event.received_at < self.source_event.occurred_at:
            raise ValueError("source event received_at must not precede occurred_at")
        for name in ("open", "high", "low", "close"):
            if not getattr(self, name).is_finite():
                raise ValueError(f"{name} must be finite")
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("candidate OHLC is inconsistent")
        if self.high < self.low:
            raise ValueError("candidate high must not be below low")


@dataclass(frozen=True)
class TradePlanPolicy:
    policy_id: str
    policy_version: str
    geometry_rule_id: str
    geometry_rule_version: str
    reward_multiple: Decimal
    maximum_entry_bars: int
    maximum_evidence_age_seconds: Decimal
    authority: AuthorityMetadata
    schema_version: str = TRADE_PLAN_POLICY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "policy_id",
            "policy_version",
            "geometry_rule_id",
            "geometry_rule_version",
        ):
            _text(name, getattr(self, name))
        if self.schema_version != TRADE_PLAN_POLICY_SCHEMA_VERSION:
            raise ValueError("unsupported trade-plan policy schema")
        if self.reward_multiple <= 0:
            raise ValueError("reward_multiple must be explicit and positive")
        if self.maximum_entry_bars <= 0:
            raise ValueError("maximum_entry_bars must be explicit and positive")
        if self.maximum_evidence_age_seconds < 0:
            raise ValueError("maximum_evidence_age_seconds must not be negative")


@dataclass(frozen=True)
class TradePlanEvidenceBinding:
    market_input: MarketInputIdentity
    candidate: StrategyCandidateIdentity
    candidate_bar: CandidateBarEvidence
    rules: EvidenceAvailability
    setups: EvidenceAvailability
    interpretation: EvidenceAvailability
    context: EvidenceAvailability
    effective_session_id: str
    entry_bar_closes: tuple[datetime, ...]
    session_ends_at: datetime
    authority: AuthorityMetadata
    schema_version: str = TRADE_PLAN_EVIDENCE_BINDING_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _text("effective_session_id", self.effective_session_id)
        _aware("session_ends_at", self.session_ends_at)
        if not self.entry_bar_closes:
            raise ValueError("entry_bar_closes must not be empty")
        for value in self.entry_bar_closes:
            _aware("entry_bar_closes", value)
        if any(
            current <= previous
            for previous, current in zip(
                self.entry_bar_closes, self.entry_bar_closes[1:]
            )
        ):
            raise ValueError("entry_bar_closes must be strictly increasing")
        if self.schema_version != TRADE_PLAN_EVIDENCE_BINDING_SCHEMA_VERSION:
            raise ValueError("unsupported evidence-binding schema")
        if self.market_input.latest_closed_at != self.candidate_bar.source_event.occurred_at:
            raise ValueError("candidate bar must bind the latest closed market event")


@dataclass(frozen=True)
class TradePlanInput:
    strategy: StrategyDecision
    evidence: TradePlanEvidenceBinding
    listed_instrument: ListedInstrument | None
    instrument_specification: InstrumentSpecification | None
    instrument_authority: AuthorityMetadata | None
    policy: TradePlanPolicy | None
    evaluated_at: datetime
    schema_version: str = TRADE_PLAN_INPUT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _aware("evaluated_at", self.evaluated_at)
        if self.schema_version != TRADE_PLAN_INPUT_SCHEMA_VERSION:
            raise ValueError("unsupported trade-plan input schema")


@dataclass(frozen=True)
class TradePlanSuccess:
    plan_id: str
    proposed_trade: ProposedTrade
    evidence: TradePlanEvidenceBinding
    expires_at: datetime
    purpose: TradePlanPurpose = TradePlanPurpose.ANALYSIS_ONLY
    execution_eligible: bool = False
    authority: TradePlanAuthority = TradePlanAuthority.PROPOSED_GEOMETRY
    requires_risk_assessment: bool = True
    requires_separate_decision: bool = True

    def __post_init__(self) -> None:
        _text("plan_id", self.plan_id)
        _aware("expires_at", self.expires_at)
        if self.proposed_trade.proposal_id != self.plan_id:
            raise ValueError("plan and proposal identity must match")
        if self.execution_eligible:
            raise ValueError("trade plans are never execution eligible")
        if not self.requires_risk_assessment or not self.requires_separate_decision:
            raise ValueError("risk assessment and a separate decision are mandatory")


@dataclass(frozen=True)
class TradePlanRefusal:
    reasons: tuple[TradePlanRefusalReason, ...]
    evaluated_at: datetime
    schema_version: str = TRADE_PLAN_REFUSAL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _aware("evaluated_at", self.evaluated_at)
        if self.schema_version != TRADE_PLAN_REFUSAL_SCHEMA_VERSION:
            raise ValueError("unsupported refusal schema")
        if not self.reasons or len(set(self.reasons)) != len(self.reasons):
            raise ValueError("refusal reasons must be non-empty and unique")


@dataclass(frozen=True)
class TradePlanResult:
    status: TradePlanStatus
    success: TradePlanSuccess | None
    refusal: TradePlanRefusal | None
    schema_version: str = TRADE_PLAN_RESULT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != TRADE_PLAN_RESULT_SCHEMA_VERSION:
            raise ValueError("unsupported result schema")
        generated = self.status == TradePlanStatus.GENERATED
        if generated != (self.success is not None) or generated == (self.refusal is not None):
            raise ValueError("result must contain exactly one complete success or refusal")
