"""Thin composition of the canonical Market Context public service."""

from datetime import datetime
from itertools import pairwise
from typing import Protocol

from atlas.core.primitives import Symbol, Timeframe
from atlas.market_context.definitions import (
    CME_RTH_V1,
    REGIME_CLASSIFIER_V1,
    RegimeClassifierDefinition,
    SessionCalendarDefinition,
)
from atlas.market_context.models import (
    ContextQuality,
    MarketContext,
    SessionClassification,
    VolatilityClassification,
    VolatilityRegime,
)
from atlas.market_context.service import build_market_context
from atlas.market_engine.models import MarketState
from atlas.trader_now.models import (
    AvailabilityStatus,
    ContextAvailability,
    ContextAvailabilityReason,
    ContextAvailabilityStatus,
    ContextMetadata,
    ContextProjection,
    MarketInputWindow,
)


class ContextEvaluator(Protocol):
    def __call__(
        self,
        *,
        symbol: Symbol,
        timeframe: Timeframe,
        occurred_at: datetime,
        window: list[MarketState],
        upstream_session_name: str | None,
        upstream_is_rth: bool | None,
        calendar: SessionCalendarDefinition,
        classifier: RegimeClassifierDefinition,
    ) -> MarketContext | None: ...


class MarketContextComposer:
    """Adapt validated raw market input to the replay-authoritative service."""

    def __init__(
        self,
        *,
        evaluator: ContextEvaluator = build_market_context,
        calendar: SessionCalendarDefinition = CME_RTH_V1,
        classifier: RegimeClassifierDefinition = REGIME_CLASSIFIER_V1,
    ) -> None:
        self._evaluator = evaluator
        self._calendar = calendar
        self._classifier = classifier

    def compose(self, market_input: MarketInputWindow) -> ContextProjection:
        if (
            market_input.availability.status != AvailabilityStatus.AVAILABLE
            or market_input.identity is None
            or not market_input.states
        ):
            return ContextProjection(
                availability=ContextAvailability(
                    ContextAvailabilityStatus.UNAVAILABLE_DUE_TO_DEPENDENCY,
                    (ContextAvailabilityReason.RAW_INPUT_UNAVAILABLE,),
                    market_input.availability.reason_codes,
                ),
                input_identity=None,
                output=None,
                metadata=None,
            )

        identity = market_input.identity
        expected_symbol = identity.market_data_series.symbol
        expected_timeframe = identity.timeframe
        source_timestamps = tuple(
            state.envelope.occurred_at for state in market_input.states
        )
        dependency_aligned = (
            source_timestamps[-1] == identity.latest_closed_at
            and all(left < right for left, right in pairwise(source_timestamps))
            and all(
                state.symbol.ticker == expected_symbol
                and state.timeframe.value == expected_timeframe
                for state in market_input.states
            )
        )
        if not dependency_aligned:
            return ContextProjection(
                availability=ContextAvailability(
                    ContextAvailabilityStatus.UNAVAILABLE_DUE_TO_DEPENDENCY,
                    (ContextAvailabilityReason.DEPENDENCY_ALIGNMENT_INVALID,),
                ),
                input_identity=None,
                output=None,
                metadata=None,
            )

        depth = self._classifier.params.lookback_bars
        source_window = market_input.states[-depth:]
        current = source_window[-1]
        upstream_session_name = (
            current.session_name.value if current.session_name is not None else None
        )
        try:
            output = self._evaluator(
                symbol=Symbol(expected_symbol),
                timeframe=Timeframe(identity.timeframe),
                occurred_at=identity.latest_closed_at,
                window=list(source_window),
                upstream_session_name=upstream_session_name,
                upstream_is_rth=current.is_rth,
                calendar=self._calendar,
                classifier=self._classifier,
            )
        except Exception:  # noqa: BLE001 - section availability owns service failures
            return self._without_output(
                ContextAvailabilityStatus.UNAVAILABLE,
                ContextAvailabilityReason.MARKET_CONTEXT_SERVICE_FAILURE,
            )
        if output is None:
            return self._without_output(
                ContextAvailabilityStatus.UNAVAILABLE,
                ContextAvailabilityReason.EMPTY_CONTEXT_OUTPUT,
            )
        if not isinstance(output, MarketContext):
            return self._without_output(
                ContextAvailabilityStatus.INVALID,
                ContextAvailabilityReason.STRUCTURALLY_INVALID,
            )

        reasons: list[ContextAvailabilityReason] = []
        structurally_valid = (
            isinstance(output.symbol, Symbol)
            and isinstance(output.timeframe, Timeframe)
            and isinstance(output.occurred_at, datetime)
            and output.occurred_at.tzinfo is not None
            and output.occurred_at.utcoffset() is not None
            and isinstance(output.session, SessionClassification)
            and isinstance(output.volatility, VolatilityClassification)
            and isinstance(output.classifier_version, str)
            and bool(output.classifier_version.strip())
            and isinstance(output.calendar_version, str)
            and bool(output.calendar_version.strip())
            and isinstance(output.context_fingerprint, str)
            and bool(output.context_fingerprint.strip())
        )
        if not structurally_valid:
            reasons.append(ContextAvailabilityReason.STRUCTURALLY_INVALID)
        if output.occurred_at != identity.latest_closed_at:
            reasons.append(ContextAvailabilityReason.TIMESTAMP_MISMATCH)
        if (
            not isinstance(output.symbol, Symbol)
            or output.symbol.ticker != expected_symbol
        ):
            reasons.append(ContextAvailabilityReason.SYMBOL_MISMATCH)
        if (
            not isinstance(output.timeframe, Timeframe)
            or output.timeframe.value != identity.timeframe
        ):
            reasons.append(ContextAvailabilityReason.TIMEFRAME_MISMATCH)
        if not isinstance(output.quality, ContextQuality):
            reasons.append(ContextAvailabilityReason.UNSUPPORTED_QUALITY)
        if reasons:
            return ContextProjection(
                availability=ContextAvailability(
                    ContextAvailabilityStatus.INVALID, tuple(reasons)
                ),
                input_identity=None,
                output=None,
                metadata=None,
            )

        status = (
            ContextAvailabilityStatus.INSUFFICIENT_DATA
            if output.volatility.regime == VolatilityRegime.INSUFFICIENT_HISTORY
            else ContextAvailabilityStatus.AVAILABLE
        )
        availability = (
            ContextAvailability(
                status, (ContextAvailabilityReason.INSUFFICIENT_HISTORY,)
            )
            if status == ContextAvailabilityStatus.INSUFFICIENT_DATA
            else ContextAvailability(status)
        )
        return ContextProjection(
            availability=availability,
            input_identity=identity,
            output=output,
            metadata=ContextMetadata.from_output(output, source_window),
        )

    @staticmethod
    def _without_output(
        status: ContextAvailabilityStatus,
        reason: ContextAvailabilityReason,
    ) -> ContextProjection:
        return ContextProjection(
            availability=ContextAvailability(status, (reason,)),
            input_identity=None,
            output=None,
            metadata=None,
        )
