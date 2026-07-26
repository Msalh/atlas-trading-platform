"""Immutable transport/domain types for the TraderNow composition boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Mapping

from atlas.market_context.models import ContextQuality, MarketContext
from atlas.market_engine.models import MarketState
from atlas.risk_projection.models import RiskProjection
from atlas.rule_engine.models import InsufficientData, RuleEngineOutput
from atlas.setup_engine.models import (
    InsufficientData as SetupInsufficientData,
)
from atlas.setup_engine.models import SetupEngineOutput
from atlas.setup_interpretation.models import (
    DirectionSource,
    SetupDirection,
    SetupInterpretation,
)
from atlas.strategy_engine.models import (
    StrategyDecision,
    StrategyDirection,
    StrategyDisposition,
)

SCHEMA_VERSION = "trader_now.v2"


class AvailabilityStatus(str, Enum):
    AVAILABLE = "available"
    NO_DATA = "no_data"
    INSUFFICIENT_DATA = "insufficient_data"
    INVALID = "invalid"
    UNAVAILABLE = "unavailable"
    NOT_APPLICABLE = "not_applicable"
    NOT_IMPLEMENTED = "not_implemented"


class TrustStatus(str, Enum):
    TRUSTED = "trusted"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class FreshnessStatus(str, Enum):
    CURRENT = "current"
    DELAYED = "delayed"
    STALE = "stale"
    INVALID = "invalid"
    UNAVAILABLE = "unavailable"
    NOT_APPLICABLE = "not_applicable"


class FreshnessReason(str, Enum):
    NO_LATEST_CLOSED_BAR = "no_latest_closed_bar"
    EXPECTED_CLOSE_UNAVAILABLE = "expected_close_unavailable"
    EXPECTED_CLOSE_NOT_APPLICABLE = "expected_close_not_applicable"
    LATEST_BAR_IN_FUTURE = "latest_bar_in_future"
    EXPECTED_CLOSE_IN_FUTURE = "expected_close_in_future"
    BAR_ARRIVAL_DELAYED = "bar_arrival_delayed"
    BAR_ARRIVAL_STALE = "bar_arrival_stale"


class StructuralValidityStatus(str, Enum):
    VALID = "valid"
    INVALID = "invalid"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class SnapshotIdentity:
    """Opaque snapshot identity; its hashing profile belongs to a later part."""

    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            raise ValueError("snapshot identity must not be blank")


@dataclass(frozen=True)
class TraderNowIdentity:
    """Explicit product and strategy identity for the approved initial scope."""

    product: str
    symbol: str
    timeframe: str
    strategy_id: str
    strategy_version: str

    def __post_init__(self) -> None:
        for field_name in (
            "product",
            "symbol",
            "timeframe",
            "strategy_id",
            "strategy_version",
        ):
            value = getattr(self, field_name)
            if not value or not value.strip():
                raise ValueError(f"{field_name} must not be blank")


@dataclass(frozen=True)
class Availability:
    """Availability is explicit and never inferred from a missing object."""

    status: AvailabilityStatus
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if any(not reason or not reason.strip() for reason in self.reason_codes):
            raise ValueError("availability reason_codes must not contain blanks")
        if self.status == AvailabilityStatus.AVAILABLE and self.reason_codes:
            raise ValueError(
                "available data must not carry unavailability reason codes"
            )


@dataclass(frozen=True)
class Trust:
    """Server-owned trust result; Part 1 can represent it but does not compute it."""

    status: TrustStatus
    policy_version: str
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.policy_version or not self.policy_version.strip():
            raise ValueError("trust policy_version must not be blank")
        if any(not reason or not reason.strip() for reason in self.reason_codes):
            raise ValueError("trust reason_codes must not contain blanks")
        if self.status == TrustStatus.TRUSTED and self.reason_codes:
            raise ValueError("trusted data must not carry degradation reason codes")


@dataclass(frozen=True)
class Freshness:
    status: FreshnessStatus
    policy_version: str
    evaluated_at: datetime
    expected_close_at: datetime | None
    latest_closed_at: datetime | None
    lateness_seconds: float | None
    reason_codes: tuple[FreshnessReason, ...] = ()

    def __post_init__(self) -> None:
        if not self.policy_version or not self.policy_version.strip():
            raise ValueError("freshness policy_version must not be blank")
        if self.evaluated_at.tzinfo is None or self.evaluated_at.utcoffset() is None:
            raise ValueError("freshness evaluated_at must be timezone-aware")
        if self.status == FreshnessStatus.CURRENT and self.reason_codes:
            raise ValueError("current freshness must not carry reason codes")
        if self.status != FreshnessStatus.CURRENT and not self.reason_codes:
            raise ValueError("non-current freshness must carry a reason code")
        if self.lateness_seconds is not None and self.lateness_seconds < 0:
            raise ValueError("lateness_seconds must not be negative")


@dataclass(frozen=True)
class RawSourceTrust:
    """Server-owned projection with each trust dimension kept explicit."""

    freshness: Freshness
    availability: AvailabilityStatus
    structural_validity: StructuralValidityStatus
    overall: TrustStatus
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.overall == TrustStatus.TRUSTED and self.reason_codes:
            raise ValueError("trusted source must not carry trust reason codes")
        if self.overall != TrustStatus.TRUSTED and not self.reason_codes:
            raise ValueError("non-trusted source must carry a trust reason code")


@dataclass(frozen=True)
class DecisionNotImplemented:
    """The only valid Decision representation before Sprint 14."""

    availability: AvailabilityStatus = AvailabilityStatus.NOT_IMPLEMENTED
    state: None = None

    def __post_init__(self) -> None:
        if self.availability != AvailabilityStatus.NOT_IMPLEMENTED:
            raise ValueError("Decision availability must remain not_implemented")


@dataclass(frozen=True)
class TraderNow:
    """Top-level read model retaining canonical composition projections."""

    snapshot: SnapshotIdentity | None
    identity: TraderNowIdentity
    trust: Trust
    availability: Mapping[str, Availability]
    decision: DecisionNotImplemented
    risk: RiskProjection | None = None
    schema_version: str = SCHEMA_VERSION
    market: MarketInputWindow | None = None
    source_trust: RawSourceTrust | None = None
    rules: RuleProjection | None = None
    setups: SetupProjection | None = None
    context: ContextProjection | None = None
    interpretations: InterpretationProjection | None = None
    strategy: StrategyProjection | None = None

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION!r}")
        if not self.availability:
            raise ValueError("availability must not be empty")
        if any(not key or not key.strip() for key in self.availability):
            raise ValueError("availability keys must not be blank")
        object.__setattr__(
            self, "availability", MappingProxyType(dict(self.availability))
        )


class MarketSourceReason(str, Enum):
    UNRESOLVED_MARKET_DATA_SERIES = "unresolved_market_data_series"
    REPOSITORY_ERROR = "repository_error"
    NO_DATA = "no_data"
    NO_CLOSED_BARS = "no_closed_bars"
    INSUFFICIENT_HISTORY = "insufficient_history"
    IDENTITY_MISMATCH = "identity_mismatch"
    TIMEFRAME_MISMATCH = "timeframe_mismatch"
    DUPLICATE_TIMESTAMPS = "duplicate_timestamps"
    OUT_OF_ORDER = "out_of_order"
    FUTURE_TIMESTAMP = "future_timestamp"
    STRUCTURALLY_INVALID = "structurally_invalid_market_state"


class MarketDataProvider(str, Enum):
    TRADINGVIEW = "tradingview"


class MarketDataSeriesType(str, Enum):
    CONTINUOUS = "continuous"
    LISTED_INSTRUMENT = "listed_instrument"


@dataclass(frozen=True)
class EconomicInstrument:
    """Vendor-neutral economic instrument family."""

    symbol: str

    def __post_init__(self) -> None:
        if not self.symbol or not self.symbol.strip():
            raise ValueError("economic instrument symbol must not be blank")


@dataclass(frozen=True)
class MarketDataSeries:
    """Provider-qualified identity of the exact persisted observation series."""

    economic_instrument: EconomicInstrument
    provider: MarketDataProvider
    symbol: str
    series_type: MarketDataSeriesType
    resolved_at: datetime
    resolution_version: str
    resolution_owner: str

    def __post_init__(self) -> None:
        for field_name in (
            "symbol",
            "resolution_version",
            "resolution_owner",
        ):
            value = getattr(self, field_name)
            if not value or not value.strip():
                raise ValueError(f"{field_name} must not be blank")
        if self.resolved_at.tzinfo is None or self.resolved_at.utcoffset() is None:
            raise ValueError("resolved_at must be timezone-aware")


@dataclass(frozen=True)
class ListedInstrument:
    """Exchange-listed contract identity; absent for continuous-only analysis."""

    economic_instrument: EconomicInstrument
    venue: str
    contract_symbol: str
    expiry: str

    def __post_init__(self) -> None:
        for field_name in ("venue", "contract_symbol", "expiry"):
            value = getattr(self, field_name)
            if not value or not value.strip():
                raise ValueError(f"{field_name} must not be blank")


@dataclass(frozen=True)
class SourceEventIdentity:
    event_id: str
    event_type: str
    source: str
    schema_version: str
    occurred_at: datetime
    received_at: datetime


@dataclass(frozen=True)
class MarketInputIdentity:
    economic_instrument: EconomicInstrument
    market_data_series: MarketDataSeries
    listed_instrument: ListedInstrument | None
    timeframe: str
    strategy_id: str
    strategy_version: str
    latest_closed_at: datetime
    observed_at: datetime
    bar_count: int
    source_events: tuple[SourceEventIdentity, ...]
    source_schema_versions: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.market_data_series.economic_instrument != self.economic_instrument:
            raise ValueError(
                "market-data series must reference the input economic instrument"
            )
        if (
            self.listed_instrument is not None
            and self.listed_instrument.economic_instrument
            != self.economic_instrument
        ):
            raise ValueError(
                "listed instrument must reference the input economic instrument"
            )
        if self.bar_count <= 0:
            raise ValueError("bar_count must be positive")
        if self.bar_count != len(self.source_events):
            raise ValueError("bar_count must match source_events")
        if not self.source_schema_versions:
            raise ValueError("source_schema_versions must not be empty")


@dataclass(frozen=True)
class MarketSourceAvailability:
    status: AvailabilityStatus
    reason_codes: tuple[MarketSourceReason, ...]
    observed_at: datetime

    def __post_init__(self) -> None:
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        if self.status == AvailabilityStatus.AVAILABLE and self.reason_codes:
            raise ValueError("available market source must not carry reason codes")
        if self.status != AvailabilityStatus.AVAILABLE and not self.reason_codes:
            raise ValueError("unavailable market source must carry a reason code")


@dataclass(frozen=True)
class MarketInputWindow:
    """Validated closed bars and truthful raw/history availability."""

    availability: MarketSourceAvailability
    history_availability: MarketSourceAvailability
    identity: MarketInputIdentity | None
    states: tuple[MarketState, ...] = ()

    def __post_init__(self) -> None:
        if len(self.states) > 288:
            raise ValueError("market input window must not exceed 288 states")
        if self.availability.status == AvailabilityStatus.AVAILABLE:
            if self.identity is None or not self.states:
                raise ValueError("available market input requires identity and states")
        elif self.identity is not None or self.states:
            raise ValueError(
                "unavailable market input must not carry identity or states"
            )


class RuleAvailabilityReason(str, Enum):
    RAW_MARKET_UNAVAILABLE = "raw_market_unavailable"
    INSUFFICIENT_HISTORY = "insufficient_history"
    RULE_ENGINE_FAILURE = "rule_engine_failure"
    RULE_OUTPUT_UNAVAILABLE = "rule_output_unavailable"
    TIMESTAMP_MISMATCH = "rule_timestamp_mismatch"
    IDENTITY_MISMATCH = "rule_identity_mismatch"
    TIMEFRAME_MISMATCH = "rule_timeframe_mismatch"


@dataclass(frozen=True)
class RuleMetadata:
    schema_version: str
    symbol: str
    timeframe: str
    occurred_at: str
    definition_versions: Mapping[str, str]
    has_insufficient_data: bool

    def __post_init__(self) -> None:
        for field_name in ("schema_version", "symbol", "timeframe", "occurred_at"):
            value = getattr(self, field_name)
            if not value or not value.strip():
                raise ValueError(f"rule metadata {field_name} must not be blank")
        if not self.definition_versions:
            raise ValueError("rule definition_versions must not be empty")
        object.__setattr__(
            self,
            "definition_versions",
            MappingProxyType(dict(self.definition_versions)),
        )

    @classmethod
    def from_output(cls, output: RuleEngineOutput) -> "RuleMetadata":
        return cls(
            schema_version=output.schema_version,
            symbol=output.symbol,
            timeframe=output.timeframe,
            occurred_at=output.occurred_at,
            definition_versions={
                fact_id: outcome.definition_version
                for fact_id, outcome in output.facts.items()
            },
            has_insufficient_data=any(
                isinstance(outcome, InsufficientData)
                for outcome in output.facts.values()
            ),
        )


@dataclass(frozen=True)
class RuleAvailability:
    status: AvailabilityStatus
    reason_codes: tuple[RuleAvailabilityReason, ...] = ()

    def __post_init__(self) -> None:
        if self.status == AvailabilityStatus.AVAILABLE and self.reason_codes:
            raise ValueError("available Rule output must not carry reason codes")
        if self.status != AvailabilityStatus.AVAILABLE and not self.reason_codes:
            raise ValueError("unavailable Rule output must carry a reason code")


@dataclass(frozen=True)
class RuleProjection:
    availability: RuleAvailability
    input_identity: MarketInputIdentity | None
    output: RuleEngineOutput | None
    metadata: RuleMetadata | None
    window: tuple[RuleEngineOutput, ...] = ()

    def __post_init__(self) -> None:
        if self.availability.status == AvailabilityStatus.AVAILABLE:
            if (
                self.input_identity is None
                or self.output is None
                or self.metadata is None
                or not self.window
            ):
                raise ValueError(
                    "available Rule projection requires input identity, output, "
                    "metadata, and window"
                )
            if self.window[-1] is not self.output:
                raise ValueError("Rule output must be the final canonical window entry")
        elif (
            self.input_identity is not None
            or self.output is not None
            or self.metadata is not None
            or self.window
        ):
            raise ValueError(
                "unavailable Rule projection must not carry output, metadata, or window"
            )


class SetupAvailabilityStatus(str, Enum):
    AVAILABLE = "available"
    INSUFFICIENT_DATA = "insufficient_data"
    INVALID = "invalid"
    UNAVAILABLE = "unavailable"
    UNAVAILABLE_DUE_TO_DEPENDENCY = "unavailable_due_to_dependency"


class SetupAvailabilityReason(str, Enum):
    RAW_INPUT_UNAVAILABLE = "raw_input_unavailable"
    RULE_OUTPUT_UNAVAILABLE = "rule_output_unavailable"
    RULE_ALIGNMENT_INVALID = "rule_alignment_invalid"
    SETUP_ENGINE_FAILURE = "setup_engine_failure"
    EMPTY_SETUP_OUTPUT = "empty_setup_output"
    INSUFFICIENT_HISTORY = "insufficient_history"
    TIMESTAMP_MISMATCH = "setup_timestamp_mismatch"
    SYMBOL_MISMATCH = "setup_symbol_mismatch"
    TIMEFRAME_MISMATCH = "setup_timeframe_mismatch"
    SETUP_TO_RULE_TIMESTAMP_MISMATCH = "setup_to_rule_timestamp_mismatch"
    STRUCTURALLY_INVALID = "structurally_invalid_setup_output"


@dataclass(frozen=True)
class RuleWindowIdentity:
    count: int
    first_occurred_at: str
    latest_occurred_at: str
    schema_versions: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.count <= 0:
            raise ValueError("Rule window count must be positive")
        if not self.first_occurred_at or not self.latest_occurred_at:
            raise ValueError("Rule window timestamps must not be blank")
        if not self.schema_versions:
            raise ValueError("Rule window schema_versions must not be empty")


@dataclass(frozen=True)
class SetupMetadata:
    schema_version: str
    symbol: str
    timeframe: str
    occurred_at: str
    definition_versions: Mapping[str, str]
    outcome_types: Mapping[str, str]
    has_insufficient_data: bool
    source_rule_window: RuleWindowIdentity

    def __post_init__(self) -> None:
        for field_name in ("schema_version", "symbol", "timeframe", "occurred_at"):
            value = getattr(self, field_name)
            if not value or not value.strip():
                raise ValueError(f"Setup metadata {field_name} must not be blank")
        if not self.definition_versions or not self.outcome_types:
            raise ValueError("Setup metadata outcome indexes must not be empty")
        object.__setattr__(
            self,
            "definition_versions",
            MappingProxyType(dict(self.definition_versions)),
        )
        object.__setattr__(
            self, "outcome_types", MappingProxyType(dict(self.outcome_types))
        )

    @classmethod
    def from_output(
        cls,
        output: SetupEngineOutput,
        rule_window: tuple[RuleEngineOutput, ...],
    ) -> "SetupMetadata":
        return cls(
            schema_version=output.schema_version,
            symbol=output.symbol,
            timeframe=output.timeframe,
            occurred_at=output.occurred_at,
            definition_versions={
                outcome.setup_name: outcome.definition_version
                for outcome in output.setups
            },
            outcome_types={
                outcome.setup_name: (
                    "insufficient_data"
                    if isinstance(outcome, SetupInsufficientData)
                    else "computed"
                )
                for outcome in output.setups
            },
            has_insufficient_data=any(
                isinstance(outcome, SetupInsufficientData) for outcome in output.setups
            ),
            source_rule_window=RuleWindowIdentity(
                count=len(rule_window),
                first_occurred_at=rule_window[0].occurred_at,
                latest_occurred_at=rule_window[-1].occurred_at,
                schema_versions=tuple(
                    sorted({entry.schema_version for entry in rule_window})
                ),
            ),
        )


@dataclass(frozen=True)
class SetupAvailability:
    status: SetupAvailabilityStatus
    reason_codes: tuple[SetupAvailabilityReason, ...] = ()
    rule_dependency_reasons: tuple[RuleAvailabilityReason, ...] = ()

    def __post_init__(self) -> None:
        if self.status == SetupAvailabilityStatus.AVAILABLE and self.reason_codes:
            raise ValueError("available Setup output must not carry reason codes")
        if self.status != SetupAvailabilityStatus.AVAILABLE and not self.reason_codes:
            raise ValueError("non-available Setup output must carry a reason code")
        if (
            self.status != SetupAvailabilityStatus.UNAVAILABLE_DUE_TO_DEPENDENCY
            and self.rule_dependency_reasons
        ):
            raise ValueError(
                "Rule dependency reasons require unavailable_due_to_dependency"
            )


@dataclass(frozen=True)
class SetupProjection:
    availability: SetupAvailability
    input_identity: MarketInputIdentity | None
    output: SetupEngineOutput | None
    metadata: SetupMetadata | None
    window: tuple[SetupEngineOutput, ...] = ()

    def __post_init__(self) -> None:
        has_output = self.availability.status in (
            SetupAvailabilityStatus.AVAILABLE,
            SetupAvailabilityStatus.INSUFFICIENT_DATA,
        )
        if has_output:
            if (
                self.input_identity is None
                or self.output is None
                or self.metadata is None
                or not self.window
            ):
                raise ValueError(
                    "available Setup projection requires identity, output, "
                    "metadata, and window"
                )
            if self.window[-1] is not self.output:
                raise ValueError(
                    "Setup output must be the final canonical window entry"
                )
        elif (
            self.input_identity is not None
            or self.output is not None
            or self.metadata is not None
            or self.window
        ):
            raise ValueError(
                "unavailable Setup projection must not carry output, metadata, "
                "or window"
            )


class ContextAvailabilityStatus(str, Enum):
    AVAILABLE = "available"
    INSUFFICIENT_DATA = "insufficient_data"
    INVALID = "invalid"
    UNAVAILABLE = "unavailable"
    UNAVAILABLE_DUE_TO_DEPENDENCY = "unavailable_due_to_dependency"


class ContextAvailabilityReason(str, Enum):
    RAW_INPUT_UNAVAILABLE = "raw_input_unavailable"
    DEPENDENCY_ALIGNMENT_INVALID = "dependency_alignment_invalid"
    MARKET_CONTEXT_SERVICE_FAILURE = "market_context_service_failure"
    EMPTY_CONTEXT_OUTPUT = "empty_context_output"
    INSUFFICIENT_HISTORY = "insufficient_history"
    TIMESTAMP_MISMATCH = "context_timestamp_mismatch"
    SYMBOL_MISMATCH = "context_symbol_mismatch"
    TIMEFRAME_MISMATCH = "context_timeframe_mismatch"
    STRUCTURALLY_INVALID = "structurally_invalid_context_output"
    UNSUPPORTED_QUALITY = "unsupported_canonical_quality_value"


@dataclass(frozen=True)
class MarketWindowIdentity:
    count: int
    first_occurred_at: datetime
    latest_occurred_at: datetime
    symbols: tuple[str, ...]
    timeframes: tuple[str, ...]
    schema_versions: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.count <= 0:
            raise ValueError("Market Context source window count must be positive")
        if self.first_occurred_at > self.latest_occurred_at:
            raise ValueError("Market Context source timestamps must be chronological")
        if not self.symbols or not self.timeframes or not self.schema_versions:
            raise ValueError("Market Context source identity indexes must not be empty")


@dataclass(frozen=True)
class ContextMetadata:
    symbol: str
    timeframe: str
    occurred_at: datetime
    classifier_version: str
    calendar_version: str
    context_fingerprint: str
    quality: ContextQuality
    source_market_window: MarketWindowIdentity

    def __post_init__(self) -> None:
        for field_name in (
            "symbol",
            "timeframe",
            "classifier_version",
            "calendar_version",
            "context_fingerprint",
        ):
            value = getattr(self, field_name)
            if not value or not value.strip():
                raise ValueError(
                    f"Market Context metadata {field_name} must not be blank"
                )

    @classmethod
    def from_output(
        cls,
        output: MarketContext,
        source_window: tuple[MarketState, ...],
    ) -> "ContextMetadata":
        return cls(
            symbol=output.symbol.ticker,
            timeframe=output.timeframe.value,
            occurred_at=output.occurred_at,
            classifier_version=output.classifier_version,
            calendar_version=output.calendar_version,
            context_fingerprint=output.context_fingerprint,
            quality=output.quality,
            source_market_window=MarketWindowIdentity(
                count=len(source_window),
                first_occurred_at=source_window[0].envelope.occurred_at,
                latest_occurred_at=source_window[-1].envelope.occurred_at,
                symbols=tuple(sorted({state.symbol.ticker for state in source_window})),
                timeframes=tuple(
                    sorted({state.timeframe.value for state in source_window})
                ),
                schema_versions=tuple(
                    sorted({state.schema_version for state in source_window})
                ),
            ),
        )


@dataclass(frozen=True)
class ContextAvailability:
    status: ContextAvailabilityStatus
    reason_codes: tuple[ContextAvailabilityReason, ...] = ()
    market_dependency_reasons: tuple[MarketSourceReason, ...] = ()

    def __post_init__(self) -> None:
        if self.status == ContextAvailabilityStatus.AVAILABLE and self.reason_codes:
            raise ValueError("available Market Context must not carry reason codes")
        if self.status != ContextAvailabilityStatus.AVAILABLE and not self.reason_codes:
            raise ValueError("non-available Market Context must carry a reason code")
        if (
            self.status != ContextAvailabilityStatus.UNAVAILABLE_DUE_TO_DEPENDENCY
            and self.market_dependency_reasons
        ):
            raise ValueError(
                "market dependency reasons require unavailable_due_to_dependency"
            )


@dataclass(frozen=True)
class ContextProjection:
    availability: ContextAvailability
    input_identity: MarketInputIdentity | None
    output: MarketContext | None
    metadata: ContextMetadata | None

    def __post_init__(self) -> None:
        has_output = self.availability.status in (
            ContextAvailabilityStatus.AVAILABLE,
            ContextAvailabilityStatus.INSUFFICIENT_DATA,
        )
        if has_output:
            if (
                self.input_identity is None
                or self.output is None
                or self.metadata is None
            ):
                raise ValueError(
                    "available Market Context requires identity, output, and metadata"
                )
        elif (
            self.input_identity is not None
            or self.output is not None
            or self.metadata is not None
        ):
            raise ValueError(
                "unavailable Market Context must not carry output or metadata"
            )


class InterpretationAvailabilityStatus(str, Enum):
    AVAILABLE = "available"
    INVALID = "invalid"
    UNAVAILABLE = "unavailable"
    UNAVAILABLE_DUE_TO_DEPENDENCY = "unavailable_due_to_dependency"


class InterpretationAvailabilityReason(str, Enum):
    RULE_DEPENDENCY_UNAVAILABLE = "rule_dependency_unavailable"
    SETUP_DEPENDENCY_UNAVAILABLE = "setup_dependency_unavailable"
    DEPENDENCY_ALIGNMENT_INVALID = "dependency_alignment_invalid"
    SERVICE_FAILURE = "interpretation_service_failure"
    EMPTY_OUTPUT = "empty_interpretation_output"
    TIMESTAMP_MISMATCH = "interpretation_timestamp_mismatch"
    SOURCE_TIMESTAMP_MISMATCH = "interpretation_source_timestamp_mismatch"
    SOURCE_SYMBOL_MISMATCH = "interpretation_source_symbol_mismatch"
    SOURCE_TIMEFRAME_MISMATCH = "interpretation_source_timeframe_mismatch"
    STRUCTURALLY_INVALID = "structurally_invalid_interpretation_output"
    UNSUPPORTED_DIRECTION = "unsupported_canonical_direction"
    UNSUPPORTED_SOURCE = "unsupported_canonical_source"


@dataclass(frozen=True)
class InterpretationSourceIdentity:
    symbol: str
    timeframe: str
    occurred_at: str
    rule_schema_version: str
    setup_schema_version: str

    def __post_init__(self) -> None:
        for field_name in (
            "symbol",
            "timeframe",
            "occurred_at",
            "rule_schema_version",
            "setup_schema_version",
        ):
            value = getattr(self, field_name)
            if not value or not value.strip():
                raise ValueError(
                    f"Interpretation source identity {field_name} must not be blank"
                )


@dataclass(frozen=True)
class InterpretationMetadata:
    occurred_at: datetime
    interpretation_versions: tuple[str, ...]
    interpretation_fingerprints: tuple[str, ...]
    setup_ids: tuple[str, ...]
    directions: Mapping[str, SetupDirection]
    sources: Mapping[str, DirectionSource]
    source_identity: InterpretationSourceIdentity

    def __post_init__(self) -> None:
        if not self.interpretation_versions:
            raise ValueError("Interpretation versions must not be empty")
        if not self.interpretation_fingerprints:
            raise ValueError("Interpretation fingerprints must not be empty")
        if not self.setup_ids:
            raise ValueError("Interpretation setup_ids must not be empty")
        if not self.directions or not self.sources:
            raise ValueError("Interpretation outcome indexes must not be empty")
        object.__setattr__(self, "directions", MappingProxyType(dict(self.directions)))
        object.__setattr__(self, "sources", MappingProxyType(dict(self.sources)))

    @classmethod
    def from_output(
        cls,
        output: tuple[SetupInterpretation, ...],
        rule_output: RuleEngineOutput,
        setup_output: SetupEngineOutput,
    ) -> "InterpretationMetadata":
        return cls(
            occurred_at=output[0].occurred_at,
            interpretation_versions=tuple(
                sorted({entry.interpretation_version for entry in output})
            ),
            interpretation_fingerprints=tuple(
                sorted({entry.interpretation_fingerprint for entry in output})
            ),
            setup_ids=tuple(entry.setup_id for entry in output),
            directions={entry.setup_id: entry.direction for entry in output},
            sources={entry.setup_id: entry.source for entry in output},
            source_identity=InterpretationSourceIdentity(
                symbol=rule_output.symbol,
                timeframe=rule_output.timeframe,
                occurred_at=rule_output.occurred_at,
                rule_schema_version=rule_output.schema_version,
                setup_schema_version=setup_output.schema_version,
            ),
        )


@dataclass(frozen=True)
class InterpretationAvailability:
    status: InterpretationAvailabilityStatus
    reason_codes: tuple[InterpretationAvailabilityReason, ...] = ()
    rule_dependency_reasons: tuple[RuleAvailabilityReason, ...] = ()
    setup_dependency_reasons: tuple[SetupAvailabilityReason, ...] = ()

    def __post_init__(self) -> None:
        if (
            self.status == InterpretationAvailabilityStatus.AVAILABLE
            and self.reason_codes
        ):
            raise ValueError("available Interpretation must not carry reason codes")
        if (
            self.status != InterpretationAvailabilityStatus.AVAILABLE
            and not self.reason_codes
        ):
            raise ValueError("non-available Interpretation must carry a reason code")
        if (
            self.status
            != InterpretationAvailabilityStatus.UNAVAILABLE_DUE_TO_DEPENDENCY
            and (self.rule_dependency_reasons or self.setup_dependency_reasons)
        ):
            raise ValueError("dependency reasons require unavailable_due_to_dependency")


@dataclass(frozen=True)
class InterpretationProjection:
    availability: InterpretationAvailability
    input_identity: MarketInputIdentity | None
    output: tuple[SetupInterpretation, ...]
    metadata: InterpretationMetadata | None

    def __post_init__(self) -> None:
        if self.availability.status == InterpretationAvailabilityStatus.AVAILABLE:
            if self.input_identity is None or not self.output or self.metadata is None:
                raise ValueError(
                    "available Interpretation requires identity, output, and metadata"
                )
        elif (
            self.input_identity is not None or self.output or self.metadata is not None
        ):
            raise ValueError(
                "unavailable Interpretation must not carry output or metadata"
            )


class StrategyAvailabilityStatus(str, Enum):
    AVAILABLE = "available"
    INVALID = "invalid"
    UNAVAILABLE = "unavailable"
    UNAVAILABLE_DUE_TO_DEPENDENCY = "unavailable_due_to_dependency"


class StrategyAvailabilityReason(str, Enum):
    RAW_INPUT_UNAVAILABLE = "raw_input_unavailable"
    RULE_DEPENDENCY_UNAVAILABLE = "rule_dependency_unavailable"
    SETUP_DEPENDENCY_UNAVAILABLE = "setup_dependency_unavailable"
    CONTEXT_DEPENDENCY_UNAVAILABLE = "context_dependency_unavailable"
    INTERPRETATION_DEPENDENCY_UNAVAILABLE = "interpretation_dependency_unavailable"
    DEPENDENCY_ALIGNMENT_INVALID = "dependency_alignment_invalid"
    DUPLICATE_SETUP_IDENTITY = "duplicate_setup_identity"
    AMBIGUOUS_INTERPRETATION_MAPPING = "ambiguous_interpretation_mapping"
    SERVICE_FAILURE = "strategy_service_failure"
    EMPTY_OUTPUT = "empty_strategy_output"
    TIMESTAMP_MISMATCH = "strategy_timestamp_mismatch"
    SYMBOL_MISMATCH = "strategy_source_symbol_mismatch"
    TIMEFRAME_MISMATCH = "strategy_source_timeframe_mismatch"
    SETUP_IDENTITY_MISMATCH = "strategy_setup_identity_mismatch"
    INTERPRETATION_IDENTITY_MISMATCH = "strategy_interpretation_identity_mismatch"
    CONTEXT_TIMESTAMP_MISMATCH = "strategy_context_timestamp_mismatch"
    CONTEXT_FINGERPRINT_MISMATCH = "strategy_context_fingerprint_mismatch"
    CONTEXT_QUALITY_MISMATCH = "strategy_context_quality_mismatch"
    STRATEGY_IDENTITY_MISMATCH = "strategy_identity_mismatch"
    STRUCTURALLY_INVALID = "structurally_invalid_strategy_output"
    UNSUPPORTED_DISPOSITION = "unsupported_canonical_strategy_disposition"
    UNSUPPORTED_DIRECTION = "unsupported_canonical_strategy_direction"


@dataclass(frozen=True)
class StrategyMetadata:
    occurred_at: datetime
    strategy_versions: Mapping[str, str]
    dispositions: Mapping[str, StrategyDisposition]
    directions: Mapping[str, StrategyDirection]
    reason_codes: Mapping[str, tuple[str, ...]]
    context_fingerprint: str
    context_quality: ContextQuality
    source_symbol: str
    source_timeframe: str
    setup_definition_versions: Mapping[str, str]
    interpretation_versions: Mapping[str, str]
    interpretation_fingerprints: Mapping[str, str]

    def __post_init__(self) -> None:
        if not self.strategy_versions:
            raise ValueError("Strategy versions must not be empty")
        if not self.context_fingerprint or not self.context_fingerprint.strip():
            raise ValueError("Strategy context fingerprint must not be blank")
        if not self.source_symbol or not self.source_timeframe:
            raise ValueError("Strategy source identity must not be blank")
        for field_name in (
            "strategy_versions",
            "dispositions",
            "directions",
            "reason_codes",
            "setup_definition_versions",
            "interpretation_versions",
            "interpretation_fingerprints",
        ):
            object.__setattr__(
                self,
                field_name,
                MappingProxyType(dict(getattr(self, field_name))),
            )


@dataclass(frozen=True)
class StrategyAvailability:
    status: StrategyAvailabilityStatus
    reason_codes: tuple[StrategyAvailabilityReason, ...] = ()
    market_dependency_reasons: tuple[MarketSourceReason, ...] = ()
    rule_dependency_reasons: tuple[RuleAvailabilityReason, ...] = ()
    setup_dependency_reasons: tuple[SetupAvailabilityReason, ...] = ()
    context_dependency_reasons: tuple[ContextAvailabilityReason, ...] = ()
    interpretation_dependency_reasons: tuple[InterpretationAvailabilityReason, ...] = ()

    def __post_init__(self) -> None:
        if self.status == StrategyAvailabilityStatus.AVAILABLE and self.reason_codes:
            raise ValueError("available Strategy must not carry reason codes")
        if (
            self.status != StrategyAvailabilityStatus.AVAILABLE
            and not self.reason_codes
        ):
            raise ValueError("non-available Strategy must carry a reason code")
        dependency_reasons = (
            self.market_dependency_reasons
            or self.rule_dependency_reasons
            or self.setup_dependency_reasons
            or self.context_dependency_reasons
            or self.interpretation_dependency_reasons
        )
        if (
            self.status != StrategyAvailabilityStatus.UNAVAILABLE_DUE_TO_DEPENDENCY
            and dependency_reasons
        ):
            raise ValueError("dependency reasons require unavailable_due_to_dependency")


@dataclass(frozen=True)
class StrategyProjection:
    availability: StrategyAvailability
    input_identity: MarketInputIdentity | None
    output: tuple[StrategyDecision, ...]
    metadata: StrategyMetadata | None

    def __post_init__(self) -> None:
        if self.availability.status == StrategyAvailabilityStatus.AVAILABLE:
            if self.input_identity is None or not self.output or self.metadata is None:
                raise ValueError(
                    "available Strategy requires identity, output, and metadata"
                )
        elif (
            self.input_identity is not None or self.output or self.metadata is not None
        ):
            raise ValueError("unavailable Strategy must not carry output or metadata")
