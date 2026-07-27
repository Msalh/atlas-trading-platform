"""Pure versioned P2B-2A runtime-authority contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Generic, TypeVar

from atlas.risk_assessment.models import InstrumentSpecification
from atlas.trade_plan.models import TradePlanPolicy
from atlas.trader_now.models import (
    EconomicInstrument,
    ListedInstrument,
    MarketDataSeries,
    MarketInputIdentity,
    SourceEventIdentity,
)

from .serialization import sha256_identity

AUTHORITY_RESOLUTION_SCHEMA_VERSION = "trade_plan_authority_resolution.v1"
AUTHORITY_SOURCE_SCHEMA_VERSION = "trade_plan_authority_source.v1"
EFFECTIVE_INTERVAL_SCHEMA_VERSION = "trade_plan_effective_interval.v1"
LISTED_CONTRACT_REQUEST_SCHEMA_VERSION = "listed_contract_authority_request.v1"
INSTRUMENT_SPECIFICATION_REQUEST_SCHEMA_VERSION = (
    "instrument_specification_authority_request.v1"
)
EXCHANGE_SESSION_REQUEST_SCHEMA_VERSION = "exchange_session_authority_request.v1"
PLAN_EXPIRY_INPUTS_SCHEMA_VERSION = "trade_plan_expiry_inputs.v1"
TRADE_PLAN_POLICY_REQUEST_SCHEMA_VERSION = "trade_plan_policy_authority_request.v1"
CANONICAL_MARKET_EVIDENCE_SCHEMA_VERSION = "canonical_market_evidence_authority.v1"

T = TypeVar("T")


def _text(name: str, value: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{name} must not be blank")


def _aware(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


class AuthorityKind(str, Enum):
    LISTED_CONTRACT = "listed_contract"
    INSTRUMENT_SPECIFICATION = "instrument_specification"
    EXCHANGE_SESSION = "exchange_session"
    TRADE_PLAN_POLICY = "trade_plan_policy"
    CANONICAL_MARKET_EVIDENCE = "canonical_market_evidence"


class AuthorityStatus(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    STALE = "stale"
    CONFLICTING = "conflicting"


class AuthorityReason(str, Enum):
    MISSING = "authority.missing"
    STALE = "authority.stale"
    OVERLAPPING = "authority.overlapping"
    CONFLICTING = "authority.conflicting"
    FUTURE_DATED = "authority.future_dated"
    UNRECONCILED = "authority.unreconciled"
    IDENTITY_MISMATCH = "authority.identity_mismatch"
    CONTINUOUS_SERIES_AS_LISTED = "authority.continuous_series_as_listed"
    MARKET_UNAVAILABLE = "authority.market_unavailable"
    MARKET_HISTORY_NOT_CANONICAL = "authority.market_history_not_canonical"
    SOURCE_EVENT_MISMATCH = "authority.source_event_mismatch"
    SOURCE_EVENT_ORDER_INVALID = "authority.source_event_order_invalid"
    CONTEXT_INSUFFICIENT_HISTORY = "authority.context_insufficient_history"


@dataclass(frozen=True)
class EffectiveInterval:
    """Half-open effective interval; unknown bounds remain explicit."""

    starts_at: datetime | None
    ends_at: datetime | None
    schema_version: str = EFFECTIVE_INTERVAL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != EFFECTIVE_INTERVAL_SCHEMA_VERSION:
            raise ValueError("unsupported effective-interval schema")
        if self.starts_at is not None:
            _aware("starts_at", self.starts_at)
        if self.ends_at is not None:
            _aware("ends_at", self.ends_at)
        if (
            self.starts_at is not None
            and self.ends_at is not None
            and self.ends_at <= self.starts_at
        ):
            raise ValueError("effective interval must be increasing")

    def contains(self, value: datetime) -> bool:
        _aware("effective-time value", value)
        return (self.starts_at is None or self.starts_at <= value) and (
            self.ends_at is None or value < self.ends_at
        )


@dataclass(frozen=True)
class AuthoritySource:
    provider_id: str
    provider_version: str
    source_id: str
    source_version: str
    observed_at: datetime
    retrieved_at: datetime
    reconciled: bool
    schema_version: str = AUTHORITY_SOURCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("provider_id", "provider_version", "source_id", "source_version"):
            _text(name, getattr(self, name))
        _aware("observed_at", self.observed_at)
        _aware("retrieved_at", self.retrieved_at)
        if self.retrieved_at < self.observed_at:
            raise ValueError("retrieved_at must not precede observed_at")
        if self.schema_version != AUTHORITY_SOURCE_SCHEMA_VERSION:
            raise ValueError("unsupported authority-source schema")


@dataclass(frozen=True)
class AuthorityRecord(Generic[T]):
    value: T
    effective_interval: EffectiveInterval
    source: AuthoritySource


def _resolution_material(
    *,
    kind: AuthorityKind,
    status: AuthorityStatus,
    evaluated_at: datetime,
    effective_interval: EffectiveInterval,
    source: AuthoritySource,
    value: object | None,
    reasons: tuple[AuthorityReason, ...],
    schema_version: str,
) -> dict[str, object]:
    return {
        "kind": kind,
        "status": status,
        "evaluated_at": evaluated_at,
        "effective_interval": effective_interval,
        "source": source,
        "value": value,
        "reasons": reasons,
        "schema_version": schema_version,
    }


@dataclass(frozen=True)
class AuthorityResolution(Generic[T]):
    kind: AuthorityKind
    status: AuthorityStatus
    resolution_id: str
    evaluated_at: datetime
    effective_interval: EffectiveInterval
    source: AuthoritySource
    value: T | None
    reasons: tuple[AuthorityReason, ...]
    schema_version: str = AUTHORITY_RESOLUTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _aware("evaluated_at", self.evaluated_at)
        _text("resolution_id", self.resolution_id)
        if self.schema_version != AUTHORITY_RESOLUTION_SCHEMA_VERSION:
            raise ValueError("unsupported authority-resolution schema")
        expected = sha256_identity(
            _resolution_material(
                kind=self.kind,
                status=self.status,
                evaluated_at=self.evaluated_at,
                effective_interval=self.effective_interval,
                source=self.source,
                value=self.value,
                reasons=self.reasons,
                schema_version=self.schema_version,
            )
        )
        if self.resolution_id != expected:
            raise ValueError("authority resolution identity mismatch")
        if self.status == AuthorityStatus.AVAILABLE:
            if self.value is None or self.reasons:
                raise ValueError(
                    "available authority requires one value and no reasons"
                )
            if (
                self.effective_interval.starts_at is None
                and self.effective_interval.ends_at is None
            ):
                raise ValueError(
                    "available authority requires a known effective interval"
                )
            if not self.source.reconciled:
                raise ValueError("available authority must be reconciled")
            if self.source.observed_at > self.evaluated_at:
                raise ValueError("available authority must not be future-observed")
            if self.source.retrieved_at > self.evaluated_at:
                raise ValueError("available authority must not be future-retrieved")
            if not self.effective_interval.contains(self.evaluated_at):
                raise ValueError(
                    "available authority must be effective at evaluation time"
                )
        else:
            if self.value is not None or not self.reasons:
                raise ValueError("non-available authority carries reasons and no value")
            if len(set(self.reasons)) != len(self.reasons):
                raise ValueError("authority reasons must be unique")
            if (
                self.status == AuthorityStatus.STALE
                and AuthorityReason.STALE not in self.reasons
            ):
                raise ValueError("stale authority requires the stale reason")


def authority_resolution(
    *,
    kind: AuthorityKind,
    status: AuthorityStatus,
    evaluated_at: datetime,
    effective_interval: EffectiveInterval,
    source: AuthoritySource,
    value: T | None = None,
    reasons: tuple[AuthorityReason, ...] = (),
) -> AuthorityResolution[T]:
    schema_version = AUTHORITY_RESOLUTION_SCHEMA_VERSION
    resolution_id = sha256_identity(
        _resolution_material(
            kind=kind,
            status=status,
            evaluated_at=evaluated_at,
            effective_interval=effective_interval,
            source=source,
            value=value,
            reasons=reasons,
            schema_version=schema_version,
        )
    )
    return AuthorityResolution(
        kind=kind,
        status=status,
        resolution_id=resolution_id,
        evaluated_at=evaluated_at,
        effective_interval=effective_interval,
        source=source,
        value=value,
        reasons=reasons,
    )


@dataclass(frozen=True)
class ListedContractAuthorityRequest:
    economic_instrument: EconomicInstrument
    analysis_series: MarketDataSeries
    evaluated_at: datetime
    schema_version: str = LISTED_CONTRACT_REQUEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _aware("evaluated_at", self.evaluated_at)
        if self.analysis_series.economic_instrument != self.economic_instrument:
            raise ValueError("analysis series economic instrument mismatch")
        if self.schema_version != LISTED_CONTRACT_REQUEST_SCHEMA_VERSION:
            raise ValueError("unsupported listed-contract request schema")


@dataclass(frozen=True)
class InstrumentSpecificationAuthorityRequest:
    listed_instrument: ListedInstrument
    evaluated_at: datetime
    schema_version: str = INSTRUMENT_SPECIFICATION_REQUEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _aware("evaluated_at", self.evaluated_at)
        if self.schema_version != INSTRUMENT_SPECIFICATION_REQUEST_SCHEMA_VERSION:
            raise ValueError("unsupported instrument-specification request schema")


@dataclass(frozen=True)
class ExchangeSessionAuthorityRequest:
    listed_instrument: ListedInstrument
    candidate_closed_at: datetime
    timeframe: str
    maximum_entry_bars: int
    evaluated_at: datetime
    schema_version: str = EXCHANGE_SESSION_REQUEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _aware("candidate_closed_at", self.candidate_closed_at)
        _aware("evaluated_at", self.evaluated_at)
        _text("timeframe", self.timeframe)
        if self.maximum_entry_bars <= 0:
            raise ValueError("maximum_entry_bars must be positive")
        if self.schema_version != EXCHANGE_SESSION_REQUEST_SCHEMA_VERSION:
            raise ValueError("unsupported exchange-session request schema")


@dataclass(frozen=True)
class PlanExpiryInputs:
    calendar_id: str
    calendar_version: str
    session_id: str
    session_opens_at: datetime
    session_ends_at: datetime
    maintenance_periods: tuple[EffectiveInterval, ...]
    eligible_entry_bar_closes: tuple[datetime, ...]
    schema_version: str = PLAN_EXPIRY_INPUTS_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("calendar_id", "calendar_version", "session_id"):
            _text(name, getattr(self, name))
        _aware("session_opens_at", self.session_opens_at)
        _aware("session_ends_at", self.session_ends_at)
        if self.session_ends_at <= self.session_opens_at:
            raise ValueError("session must be increasing")
        if not self.eligible_entry_bar_closes:
            raise ValueError("eligible entry closes must not be empty")
        for value in self.eligible_entry_bar_closes:
            _aware("eligible_entry_bar_closes", value)
            if not self.session_opens_at < value <= self.session_ends_at:
                raise ValueError("eligible entry close must be within the session")
        if any(
            current <= previous
            for previous, current in zip(
                self.eligible_entry_bar_closes,
                self.eligible_entry_bar_closes[1:],
            )
        ):
            raise ValueError("eligible entry closes must be strictly increasing")
        for period in self.maintenance_periods:
            if (
                period.starts_at is None
                or period.ends_at is None
                or period.starts_at < self.session_opens_at
                or period.ends_at > self.session_ends_at
            ):
                raise ValueError("maintenance periods must be bounded by the session")
        if self.schema_version != PLAN_EXPIRY_INPUTS_SCHEMA_VERSION:
            raise ValueError("unsupported plan-expiry schema")


@dataclass(frozen=True)
class TradePlanPolicyAuthorityRequest:
    economic_instrument: EconomicInstrument
    strategy_id: str
    strategy_version: str
    evaluated_at: datetime
    schema_version: str = TRADE_PLAN_POLICY_REQUEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("strategy_id", "strategy_version"):
            _text(name, getattr(self, name))
        _aware("evaluated_at", self.evaluated_at)
        if self.schema_version != TRADE_PLAN_POLICY_REQUEST_SCHEMA_VERSION:
            raise ValueError("unsupported trade-plan-policy request schema")


@dataclass(frozen=True)
class CanonicalMarketEvidence:
    market_input: MarketInputIdentity
    latest_source_event: SourceEventIdentity
    source_event_ids: tuple[str, ...]
    source_event_timestamps: tuple[datetime, ...]
    schema_version: str = CANONICAL_MARKET_EVIDENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CANONICAL_MARKET_EVIDENCE_SCHEMA_VERSION:
            raise ValueError("unsupported canonical-market-evidence schema")
        if self.market_input.bar_count != 288:
            raise ValueError(
                "canonical market evidence requires exactly 288 observations"
            )
        if (
            len(self.source_event_ids) != 288
            or len(self.source_event_timestamps) != 288
        ):
            raise ValueError(
                "canonical source lineage requires exactly 288 observations"
            )
        if len(set(self.source_event_ids)) != 288:
            raise ValueError("canonical source event identities must be unique")
        if any(
            current <= previous
            for previous, current in zip(
                self.source_event_timestamps, self.source_event_timestamps[1:]
            )
        ):
            raise ValueError("canonical source timestamps must be chronological")
        if self.latest_source_event != self.market_input.source_events[-1]:
            raise ValueError("latest source event must match market input identity")
        if self.latest_source_event.occurred_at != self.market_input.latest_closed_at:
            raise ValueError("latest source event timestamp must match market input")
        if self.source_event_ids != tuple(
            event.event_id for event in self.market_input.source_events
        ):
            raise ValueError("source event identities must match market input")
        if self.source_event_timestamps != tuple(
            event.occurred_at for event in self.market_input.source_events
        ):
            raise ValueError("source event timestamps must match market input")


ListedContractResolution = AuthorityResolution[ListedInstrument]
InstrumentSpecificationResolution = AuthorityResolution[InstrumentSpecification]
ExchangeSessionResolution = AuthorityResolution[PlanExpiryInputs]
TradePlanPolicyResolution = AuthorityResolution[TradePlanPolicy]
CanonicalMarketEvidenceResolution = AuthorityResolution[CanonicalMarketEvidence]
