"""Pure Product P2A contracts for proposed-trade and risk-input authority."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Generic, TypeVar

from atlas.core.primitives import Price
from atlas.risk_assessment.models import SourceProvenance
from atlas.strategy_engine.models import StrategyDecision, StrategyDirection
from atlas.trader_now.models import (
    EconomicInstrument,
    ListedInstrument,
    MarketDataSeries,
)

PROPOSED_TRADE_SCHEMA_VERSION = "proposed_trade.v1"
AUTHORITY_METADATA_SCHEMA_VERSION = "risk_input_authority.v1"
T = TypeVar("T")


def _text(name: str, value: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{name} must not be blank")


def _aware(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


class SourceAuthority(str, Enum):
    AUTHORITATIVE = "authoritative"
    CONFIGURED = "configured"
    DELAYED = "delayed"
    INFERRED = "inferred"
    MOCKED = "mocked"
    UNAVAILABLE = "unavailable"


class QuantityResolution(str, Enum):
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"


class AlignmentReason(str, Enum):
    STRATEGY_NOT_CANDIDATE = "proposal.strategy.not_candidate"
    CANDIDATE_IDENTITY_MISMATCH = "proposal.strategy.identity_mismatch"
    CANDIDATE_TIMESTAMP_MISMATCH = "proposal.strategy.timestamp_mismatch"
    CANDIDATE_DIRECTION_MISMATCH = "proposal.strategy.direction_mismatch"
    ECONOMIC_INSTRUMENT_MISMATCH = "proposal.identity.economic_instrument_mismatch"
    SOURCE_SERIES_MISMATCH = "proposal.identity.source_series_mismatch"
    LISTED_INSTRUMENT_MISSING = "proposal.identity.listed_instrument_missing"
    LISTED_INSTRUMENT_MISMATCH = "proposal.identity.listed_instrument_mismatch"
    CONTINUOUS_SERIES_AS_CONTRACT = "proposal.identity.continuous_series_as_contract"
    TARGET_REQUIRED = "proposal.geometry.target_required"
    QUANTITY_UNRESOLVED = "proposal.quantity.unresolved"
    PROPOSAL_STALE = "proposal.freshness.stale"
    PROPOSAL_FUTURE = "proposal.freshness.future"
    SOURCE_NOT_AUTHORITATIVE = "proposal.source.not_authoritative"
    SOURCE_UNRECONCILED = "proposal.source.unreconciled"
    RISK_INPUT_MISMATCH = "proposal.risk_input.mismatch"


@dataclass(frozen=True)
class AuthorityMetadata:
    authority: SourceAuthority
    provenance: SourceProvenance
    observed_at: datetime
    received_at: datetime
    reconciled: bool
    schema_version: str = AUTHORITY_METADATA_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _aware("observed_at", self.observed_at)
        _aware("received_at", self.received_at)
        _text("schema_version", self.schema_version)
        if self.received_at < self.observed_at:
            raise ValueError("received_at must not precede observed_at")
        if self.authority == SourceAuthority.AUTHORITATIVE and not self.reconciled:
            raise ValueError("authoritative source metadata must be reconciled")


@dataclass(frozen=True)
class AuthoritativeValue(Generic[T]):
    """A value plus explicit authority classification; absence stays explicit."""

    value: T | None
    metadata: AuthorityMetadata

    def __post_init__(self) -> None:
        if self.metadata.authority == SourceAuthority.UNAVAILABLE:
            if self.value is not None:
                raise ValueError("unavailable authority must not carry a value")
        elif self.value is None:
            raise ValueError("available authority classification requires a value")


@dataclass(frozen=True)
class StrategyCandidateIdentity:
    occurred_at: datetime
    strategy_id: str
    strategy_version: str
    setup_ids: tuple[str, ...]
    context_fingerprint: str
    direction: StrategyDirection

    def __post_init__(self) -> None:
        _aware("occurred_at", self.occurred_at)
        for name in ("strategy_id", "strategy_version", "context_fingerprint"):
            _text(name, getattr(self, name))
        if not self.setup_ids or len(set(self.setup_ids)) != len(self.setup_ids):
            raise ValueError("setup_ids must be non-empty and unique")
        if self.direction not in (StrategyDirection.LONG, StrategyDirection.SHORT):
            raise ValueError("candidate direction must be long or short")

    @classmethod
    def from_decision(cls, decision: StrategyDecision) -> StrategyCandidateIdentity:
        from atlas.strategy_engine.models import StrategyDisposition

        if decision.disposition != StrategyDisposition.CANDIDATE:
            raise ValueError("only a Strategy candidate has candidate identity")
        return cls(
            occurred_at=decision.occurred_at,
            strategy_id=decision.strategy_id,
            strategy_version=decision.strategy_version,
            setup_ids=decision.setup_ids,
            context_fingerprint=decision.context_fingerprint,
            direction=decision.direction,
        )


@dataclass(frozen=True)
class ProposedTrade:
    proposal_id: str
    candidate: StrategyCandidateIdentity
    economic_instrument: EconomicInstrument
    analysis_series: MarketDataSeries
    listed_instrument: ListedInstrument
    direction: StrategyDirection
    entry_type: str
    entry: Price
    stop: Price
    target: Price | None
    invalidation: Price | None
    quantity_resolution: QuantityResolution
    requested_quantity: int | None
    created_at: datetime
    evaluated_at: datetime
    rule_id: str
    rule_version: str
    authority: AuthorityMetadata
    schema_version: str = PROPOSED_TRADE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "proposal_id",
            "entry_type",
            "rule_id",
            "rule_version",
            "schema_version",
        ):
            _text(name, getattr(self, name))
        _aware("created_at", self.created_at)
        _aware("evaluated_at", self.evaluated_at)
        if self.created_at < self.candidate.occurred_at:
            raise ValueError("created_at must not precede the Strategy candidate")
        if self.evaluated_at < self.created_at:
            raise ValueError("evaluated_at must not precede created_at")
        if self.authority.observed_at > self.created_at:
            raise ValueError("proposal provenance must be observed by created_at")
        if self.analysis_series.economic_instrument != self.economic_instrument:
            raise ValueError("analysis series economic instrument mismatch")
        if self.listed_instrument.economic_instrument != self.economic_instrument:
            raise ValueError("listed instrument economic instrument mismatch")
        if self.direction != self.candidate.direction:
            raise ValueError("proposal direction must match candidate direction")
        if (
            self.analysis_series.symbol
            == self.listed_instrument.contract_symbol
            and self.analysis_series.series_type.value == "continuous"
        ):
            raise ValueError("continuous analysis series cannot be the listed contract")
        if self.quantity_resolution == QuantityResolution.RESOLVED:
            if self.requested_quantity is None or self.requested_quantity <= 0:
                raise ValueError("resolved quantity requires a positive value")
        elif self.requested_quantity is not None:
            raise ValueError("unresolved quantity must not carry a value")


@dataclass(frozen=True)
class AlignmentResult:
    reasons: tuple[AlignmentReason, ...]

    @property
    def accepted(self) -> bool:
        return not self.reasons
