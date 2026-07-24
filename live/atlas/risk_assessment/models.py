"""Immutable V1 contracts for broker-neutral candidate risk assessment.

This module stores inputs and outputs only. It does not classify freshness,
evaluate policy, calculate risk or quantity, or perform alignment.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from atlas.core.primitives import Price
from atlas.strategy_engine.models import StrategyDecision

ACCOUNT_SNAPSHOT_SCHEMA_VERSION = "risk_account_snapshot.v1"
POSITION_SNAPSHOT_SCHEMA_VERSION = "risk_position_snapshot.v1"
INSTRUMENT_SCHEMA_VERSION = "risk_instrument_specification.v1"
FRESHNESS_POLICY_SCHEMA_VERSION = "risk_snapshot_freshness_policy.v1"
RISK_POLICY_SCHEMA_VERSION = "risk_policy.v1"
CANDIDATE_SCHEMA_VERSION = "risk_candidate_trade_input.v1"
RISK_INPUT_SCHEMA_VERSION = "risk_assessment_input.v1"
ASSESSMENT_SCHEMA_VERSION = "risk_assessment.v1"
REASON_VOCABULARY_VERSION = "risk_reasons.v1"


def _require_text(field_name: str, value: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{field_name} must not be blank")


def _require_aware(field_name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _require_nonnegative(field_name: str, value: Decimal | int) -> None:
    if value < 0:
        raise ValueError(f"{field_name} must not be negative")


class AssessmentStatus(str, Enum):
    APPROVED = "approved"
    BLOCKED = "blocked"
    UNASSESSABLE = "unassessable"
    NOT_APPLICABLE = "not_applicable"


class FreshnessStatus(str, Enum):
    CURRENT = "current"
    DELAYED = "delayed"
    STALE = "stale"
    INVALID = "invalid"
    UNAVAILABLE = "unavailable"
    NOT_APPLICABLE = "not_applicable"


class ReconciliationStatus(str, Enum):
    RECONCILED = "reconciled"
    UNRECONCILED = "unreconciled"


class PositionSide(str, Enum):
    FLAT = "flat"
    LONG = "long"
    SHORT = "short"


class KillSwitchStatus(str, Enum):
    INACTIVE = "inactive"
    ACTIVE = "active"


class SizingMode(str, Enum):
    FIXED = "fixed"
    RISK_BASED = "risk_based"


class RiskAuthority(str, Enum):
    ADVISORY = "advisory"


class RiskReason(str, Enum):
    ACCOUNT_MISSING = "risk.account.missing"
    ACCOUNT_STALE = "risk.account.stale"
    ACCOUNT_INVALID = "risk.account.invalid"
    ACCOUNT_UNRECONCILED = "risk.account.unreconciled"
    POSITION_MISSING = "risk.position.missing"
    POSITION_STALE = "risk.position.stale"
    POSITION_UNRECONCILED = "risk.position.unreconciled"
    INSTRUMENT_MISSING = "risk.instrument.missing"
    POLICY_MISSING = "risk.policy.missing"
    IDENTITY_MISMATCH = "risk.identity.mismatch"
    TIMESTAMP_MISMATCH = "risk.timestamp.mismatch"
    SESSION_MISMATCH = "risk.session.mismatch"
    CANDIDATE_NOT_APPLICABLE = "risk.candidate.not_applicable"
    CANDIDATE_UNSUPPORTED_DIRECTION = "risk.candidate.unsupported_direction"
    CANDIDATE_ENTRY_MISSING = "risk.candidate.entry_missing"
    CANDIDATE_STOP_MISSING = "risk.candidate.stop_missing"
    CANDIDATE_TARGET_MISSING = "risk.candidate.target_missing"
    CANDIDATE_LEVEL_MISMATCH = "risk.candidate.level_mismatch"
    CANDIDATE_INVALID_STOP_GEOMETRY = "risk.candidate.invalid_stop_geometry"
    CANDIDATE_ZERO_STOP_DISTANCE = "risk.candidate.zero_stop_distance"
    CANDIDATE_EXPIRED = "risk.candidate.expired"
    ACCOUNT_KILL_SWITCH_ACTIVE = "risk.account.kill_switch_active"
    DAILY_LOSS_BREACHED = "risk.limit.daily_loss_breached"
    TRAILING_DRAWDOWN_BREACHED = "risk.limit.trailing_drawdown_breached"
    INSUFFICIENT_REMAINING_RISK = "risk.capacity.insufficient_remaining_risk"
    MAXIMUM_QUANTITY_EXCEEDED = "risk.quantity.maximum_exceeded"
    ZERO_APPROVED_QUANTITY = "risk.quantity.zero_approved"
    MAXIMUM_EXPOSURE_EXCEEDED = "risk.exposure.maximum_exceeded"
    CONCURRENT_POSITION_LIMIT = "risk.exposure.concurrent_position_limit"
    WORKING_ORDER_LIMIT = "risk.exposure.working_order_limit"
    OPPOSITE_POSITION = "risk.exposure.opposite_position"
    MARGIN_UNKNOWN = "risk.margin.unknown"
    MARGIN_INSUFFICIENT = "risk.margin.insufficient"
    SESSION_INELIGIBLE = "risk.session.ineligible"


@dataclass(frozen=True)
class SourceProvenance:
    source_id: str
    source_version: str
    source_object_id: str
    source_sequence: str | None = None

    def __post_init__(self) -> None:
        _require_text("source_id", self.source_id)
        _require_text("source_version", self.source_version)
        _require_text("source_object_id", self.source_object_id)
        if self.source_sequence is not None:
            _require_text("source_sequence", self.source_sequence)


@dataclass(frozen=True)
class AccountSnapshot:
    snapshot_id: str
    account_id: str
    provider_id: str
    observed_at: datetime
    received_at: datetime
    effective_session_id: str
    currency: str
    net_liquidation: Decimal
    daily_realized_pnl: Decimal
    account_status: str
    kill_switch_status: KillSwitchStatus
    reconciliation_status: ReconciliationStatus
    provenance: SourceProvenance
    cash_balance: Decimal | None = None
    realized_pnl: Decimal | None = None
    unrealized_pnl: Decimal | None = None
    high_water_mark: Decimal | None = None
    available_buying_power: Decimal | None = None
    available_margin: Decimal | None = None
    schema_version: str = ACCOUNT_SNAPSHOT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "snapshot_id",
            "account_id",
            "provider_id",
            "effective_session_id",
            "currency",
            "account_status",
            "schema_version",
        ):
            _require_text(name, getattr(self, name))
        _require_aware("observed_at", self.observed_at)
        _require_aware("received_at", self.received_at)
        if self.received_at < self.observed_at:
            raise ValueError("received_at must not precede observed_at")


@dataclass(frozen=True)
class PositionSnapshot:
    snapshot_id: str
    account_id: str
    product: str
    contract_symbol: str
    side: PositionSide
    net_quantity: int
    observed_at: datetime
    received_at: datetime
    broker_position_status: str
    reconciliation_status: ReconciliationStatus
    provenance: SourceProvenance
    average_entry_price: Price | None = None
    unrealized_pnl: Decimal | None = None
    lifecycle_realized_pnl: Decimal | None = None
    opened_at: datetime | None = None
    protective_stop: Price | None = None
    protective_stop_quantity: int = 0
    target: Price | None = None
    target_quantity: int = 0
    working_entry_quantity: int = 0
    working_exit_quantity: int = 0
    pending_cancel_or_amend: bool = False
    schema_version: str = POSITION_SNAPSHOT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "snapshot_id",
            "account_id",
            "product",
            "contract_symbol",
            "broker_position_status",
            "schema_version",
        ):
            _require_text(name, getattr(self, name))
        _require_aware("observed_at", self.observed_at)
        _require_aware("received_at", self.received_at)
        if self.received_at < self.observed_at:
            raise ValueError("received_at must not precede observed_at")
        if self.opened_at is not None:
            _require_aware("opened_at", self.opened_at)
            if self.opened_at > self.observed_at:
                raise ValueError("opened_at must not follow observed_at")
        for name in (
            "net_quantity",
            "protective_stop_quantity",
            "target_quantity",
            "working_entry_quantity",
            "working_exit_quantity",
        ):
            _require_nonnegative(name, getattr(self, name))
        if self.side == PositionSide.FLAT:
            if self.net_quantity != 0 or self.average_entry_price is not None:
                raise ValueError(
                    "flat position requires zero net_quantity and no average_entry_price"
                )
        elif self.net_quantity == 0 or self.average_entry_price is None:
            raise ValueError(
                "non-flat position requires positive net_quantity and average_entry_price"
            )


@dataclass(frozen=True)
class InstrumentSpecification:
    specification_id: str
    product: str
    contract_symbol: str
    asset_class: str
    exchange: str
    currency: str
    tick_size: Decimal
    tick_value: Decimal
    point_value: Decimal
    contract_multiplier: Decimal
    minimum_quantity: int
    quantity_increment: int
    price_precision: int
    session_calendar_id: str
    provenance: SourceProvenance
    maximum_platform_quantity: int | None = None
    margin_per_contract: Decimal | None = None
    schema_version: str = INSTRUMENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "specification_id",
            "product",
            "contract_symbol",
            "asset_class",
            "exchange",
            "currency",
            "session_calendar_id",
            "schema_version",
        ):
            _require_text(name, getattr(self, name))
        for name in ("tick_size", "tick_value", "point_value", "contract_multiplier"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.minimum_quantity <= 0 or self.quantity_increment <= 0:
            raise ValueError("quantity minimum and increment must be positive")
        _require_nonnegative("price_precision", self.price_precision)
        if self.maximum_platform_quantity is not None:
            if self.maximum_platform_quantity < self.minimum_quantity:
                raise ValueError(
                    "maximum_platform_quantity must not be below minimum_quantity"
                )
        if self.margin_per_contract is not None:
            _require_nonnegative("margin_per_contract", self.margin_per_contract)


@dataclass(frozen=True)
class SnapshotFreshnessPolicy:
    policy_id: str
    policy_version: str
    account_max_age_seconds: Decimal
    position_max_age_seconds: Decimal
    candidate_max_age_seconds: Decimal
    max_source_receive_delay_seconds: Decimal
    allowed_future_skew_seconds: Decimal
    require_same_session: bool
    provenance: SourceProvenance
    schema_version: str = FRESHNESS_POLICY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("policy_id", "policy_version", "schema_version"):
            _require_text(name, getattr(self, name))
        for name in (
            "account_max_age_seconds",
            "position_max_age_seconds",
            "candidate_max_age_seconds",
            "max_source_receive_delay_seconds",
            "allowed_future_skew_seconds",
        ):
            _require_nonnegative(name, getattr(self, name))


@dataclass(frozen=True)
class RiskPolicy:
    policy_id: str
    policy_version: str
    account_profile_id: str
    authority: RiskAuthority
    sizing_mode: SizingMode
    freshness_policy_id: str
    maximum_quantity: int
    maximum_open_position_quantity: int
    maximum_working_order_quantity: int
    maximum_concurrent_positions: int
    minimum_remaining_daily_risk: Decimal
    daily_loss_limit: Decimal
    trailing_drawdown_limit: Decimal | None
    block_same_direction_additions: bool
    block_opposite_positions: bool
    working_orders_count_as_exposure: bool
    require_target: bool
    enforce_margin: bool
    no_trade_account_statuses: tuple[str, ...]
    eligible_session_ids: tuple[str, ...]
    provenance: SourceProvenance
    maximum_risk_per_trade: Decimal | None = None
    maximum_risk_fraction: Decimal | None = None
    schema_version: str = RISK_POLICY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "policy_id",
            "policy_version",
            "account_profile_id",
            "freshness_policy_id",
            "schema_version",
        ):
            _require_text(name, getattr(self, name))
        for name in (
            "maximum_quantity",
            "maximum_open_position_quantity",
            "maximum_working_order_quantity",
            "maximum_concurrent_positions",
        ):
            _require_nonnegative(name, getattr(self, name))
        for name in ("minimum_remaining_daily_risk", "daily_loss_limit"):
            _require_nonnegative(name, getattr(self, name))
        if self.trailing_drawdown_limit is not None:
            _require_nonnegative(
                "trailing_drawdown_limit", self.trailing_drawdown_limit
            )
        if self.maximum_risk_per_trade is not None:
            _require_nonnegative("maximum_risk_per_trade", self.maximum_risk_per_trade)
        if self.maximum_risk_fraction is not None:
            _require_nonnegative("maximum_risk_fraction", self.maximum_risk_fraction)
        if len(set(self.no_trade_account_statuses)) != len(
            self.no_trade_account_statuses
        ):
            raise ValueError("no_trade_account_statuses must not contain duplicates")
        if len(set(self.eligible_session_ids)) != len(self.eligible_session_ids):
            raise ValueError("eligible_session_ids must not contain duplicates")
        for status in self.no_trade_account_statuses:
            _require_text("no_trade_account_status", status)
        for session_id in self.eligible_session_ids:
            _require_text("eligible_session_id", session_id)


@dataclass(frozen=True)
class CandidateTradeInput:
    candidate_id: str
    strategy_id: str
    strategy_version: str
    context_fingerprint: str
    product: str
    contract_symbol: str
    candidate_at: datetime
    direction: str
    entry_type: str
    entry: Price
    stop: Price
    provenance: SourceProvenance
    target: Price | None = None
    invalidation: Price | None = None
    requested_quantity: int | None = None
    schema_version: str = CANDIDATE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "candidate_id",
            "strategy_id",
            "strategy_version",
            "context_fingerprint",
            "product",
            "contract_symbol",
            "direction",
            "entry_type",
            "schema_version",
        ):
            _require_text(name, getattr(self, name))
        _require_aware("candidate_at", self.candidate_at)
        if self.requested_quantity is not None:
            _require_nonnegative("requested_quantity", self.requested_quantity)


@dataclass(frozen=True)
class RiskAssessmentInput:
    input_id: str
    snapshot_id: str
    strategy_decision: StrategyDecision
    candidate: CandidateTradeInput
    freshness_policy: SnapshotFreshnessPolicy
    evaluated_at: datetime
    effective_session_id: str
    latest_closed_at: datetime
    account: AccountSnapshot | None
    positions: tuple[PositionSnapshot, ...]
    instrument: InstrumentSpecification | None
    policy: RiskPolicy | None
    schema_version: str = RISK_INPUT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "input_id",
            "snapshot_id",
            "effective_session_id",
            "schema_version",
        ):
            _require_text(name, getattr(self, name))
        _require_aware("evaluated_at", self.evaluated_at)
        _require_aware("latest_closed_at", self.latest_closed_at)
        position_ids = tuple(position.snapshot_id for position in self.positions)
        if len(set(position_ids)) != len(position_ids):
            raise ValueError("positions must not contain duplicate snapshot identities")
        position_keys = tuple(
            (position.account_id, position.contract_symbol)
            for position in self.positions
        )
        if len(set(position_keys)) != len(position_keys):
            raise ValueError(
                "positions must not contain duplicate account/contract identities"
            )


@dataclass(frozen=True)
class AssessmentIdentity:
    assessment_id: str
    input_id: str
    snapshot_id: str
    candidate_id: str
    account_snapshot_id: str | None
    policy_id: str | None
    policy_version: str | None

    def __post_init__(self) -> None:
        for name in ("assessment_id", "input_id", "snapshot_id", "candidate_id"):
            _require_text(name, getattr(self, name))
        if (self.policy_id is None) != (self.policy_version is None):
            raise ValueError(
                "policy_id and policy_version must either both be present or both absent"
            )
        if self.account_snapshot_id is not None:
            _require_text("account_snapshot_id", self.account_snapshot_id)
        if self.policy_id is not None:
            _require_text("policy_id", self.policy_id)
            _require_text("policy_version", self.policy_version or "")


@dataclass(frozen=True)
class RiskAssessment:
    identity: AssessmentIdentity
    assessed_at: datetime
    candidate_at: datetime
    status: AssessmentStatus
    primary_reason: RiskReason | None
    contributing_reasons: tuple[RiskReason, ...]
    summaries: tuple[str, ...]
    direction: str
    entry: Price
    stop: Price
    sizing_mode: SizingMode | None
    requested_quantity: int | None
    maximum_approved_quantity: int | None
    approved_quantity: int | None
    risk_points: Decimal | None
    risk_ticks: int | None
    risk_per_contract: Decimal | None
    total_candidate_risk: Decimal | None
    remaining_daily_risk: Decimal | None
    remaining_drawdown: Decimal | None
    exposure_before: int | None
    exposure_after: int | None
    account_freshness: FreshnessStatus
    position_freshness: FreshnessStatus
    candidate_freshness: FreshnessStatus
    reconciliation_status: ReconciliationStatus | None
    source_identities: tuple[str, ...]
    target: Price | None = None
    invalidation: Price | None = None
    reason_vocabulary_version: str = REASON_VOCABULARY_VERSION
    schema_version: str = ASSESSMENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "direction",
            "reason_vocabulary_version",
            "schema_version",
        ):
            _require_text(name, getattr(self, name))
        _require_aware("assessed_at", self.assessed_at)
        _require_aware("candidate_at", self.candidate_at)
        if self.assessed_at < self.candidate_at:
            raise ValueError("assessed_at must not precede candidate_at")
        if (
            self.primary_reason is not None
            and self.primary_reason in self.contributing_reasons
        ):
            raise ValueError(
                "primary_reason must not be repeated in contributing_reasons"
            )
        if len(set(self.contributing_reasons)) != len(self.contributing_reasons):
            raise ValueError("contributing_reasons must not contain duplicates")
        if len(set(self.source_identities)) != len(self.source_identities):
            raise ValueError("source_identities must not contain duplicates")
        for summary in self.summaries:
            _require_text("summary", summary)
        for source_identity in self.source_identities:
            _require_text("source_identity", source_identity)
        for name in (
            "requested_quantity",
            "maximum_approved_quantity",
            "approved_quantity",
            "risk_ticks",
            "exposure_before",
            "exposure_after",
        ):
            value = getattr(self, name)
            if value is not None:
                _require_nonnegative(name, value)
        for name in (
            "risk_points",
            "risk_per_contract",
            "total_candidate_risk",
        ):
            value = getattr(self, name)
            if value is not None:
                _require_nonnegative(name, value)
