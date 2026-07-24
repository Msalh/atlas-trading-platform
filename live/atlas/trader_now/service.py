"""TraderNow application boundary and read-only composition."""

from dataclasses import replace
from datetime import datetime, timedelta

from atlas.core.primitives import Symbol, Timeframe
from atlas.market_engine.models import BarStatus, MarketState
from atlas.market_engine.ports import MarketStateRepository
from atlas.risk_assessment.models import RiskAssessmentInput
from atlas.risk_assessment.service import assess_candidate_risk
from atlas.risk_projection.projection import project_risk_assessment
from atlas.strategy_engine.models import StrategyDecision
from atlas.trader_now.errors import (
    MarketDataSeriesResolutionError,
    RiskCompositionAlignmentError,
)
from atlas.trader_now.identity import validate_identity
from atlas.trader_now.models import (
    AvailabilityStatus,
    MarketInputIdentity,
    MarketInputWindow,
    MarketSourceAvailability,
    MarketSourceReason,
    SourceEventIdentity,
    TraderNow,
    TraderNowIdentity,
)
from atlas.trader_now.ports import Clock, MarketDataSeriesResolver

MAX_MARKET_STATES = 288
FUTURE_TIMESTAMP_TOLERANCE = timedelta(seconds=5)


class TraderNowService:
    """Permanent orchestration entry point for explicit immutable inputs."""

    def validate_request(
        self,
        *,
        symbol: str,
        timeframe: str,
        strategy_id: str,
    ) -> TraderNowIdentity:
        return validate_identity(symbol, timeframe, strategy_id)

    def compose_risk(
        self,
        result: TraderNow,
        *,
        strategy_decisions: tuple[StrategyDecision, ...] = (),
        risk_input: RiskAssessmentInput | None = None,
    ) -> TraderNow:
        """Attach canonical read-only risk output when explicit input is supplied."""
        if risk_input is None:
            return result

        match_count = sum(
            decision == risk_input.strategy_decision for decision in strategy_decisions
        )
        if match_count != 1:
            raise RiskCompositionAlignmentError(match_count)

        assessment = assess_candidate_risk(risk_input)
        return replace(result, risk=project_risk_assessment(assessment))


class MarketInputAcquirer:
    """Acquire and validate raw closed MarketState inputs only."""

    def __init__(
        self,
        *,
        repository: MarketStateRepository,
        market_data_series_resolver: MarketDataSeriesResolver,
        clock: Clock,
    ) -> None:
        self._repository = repository
        self._market_data_series_resolver = market_data_series_resolver
        self._clock = clock

    async def acquire(self, identity: TraderNowIdentity) -> MarketInputWindow:
        observed_at = self._clock()
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")

        try:
            series = self._market_data_series_resolver.resolve(
                identity.product, observed_at
            )
        except MarketDataSeriesResolutionError:
            return self._unavailable(
                observed_at,
                AvailabilityStatus.UNAVAILABLE,
                MarketSourceReason.UNRESOLVED_MARKET_DATA_SERIES,
            )

        try:
            rows = await self._repository.get_history(
                Symbol(series.symbol),
                Timeframe.M5,
                limit=MAX_MARKET_STATES,
            )
        except Exception:
            return self._unavailable(
                observed_at,
                AvailabilityStatus.UNAVAILABLE,
                MarketSourceReason.REPOSITORY_ERROR,
            )

        if not rows:
            return self._unavailable(
                observed_at,
                AvailabilityStatus.NO_DATA,
                MarketSourceReason.NO_DATA,
            )

        structural_reason = self._validate_structure(
            rows, series.symbol, observed_at
        )
        if structural_reason is not None:
            return self._unavailable(
                observed_at, AvailabilityStatus.INVALID, structural_reason
            )

        closed = [state for state in rows if state.bar_status == BarStatus.CLOSED]
        if not closed:
            return self._unavailable(
                observed_at,
                AvailabilityStatus.NO_DATA,
                MarketSourceReason.NO_CLOSED_BARS,
            )

        try:
            chronological = sorted(closed, key=lambda state: state.envelope.occurred_at)
        except (AttributeError, TypeError):
            return self._unavailable(
                observed_at,
                AvailabilityStatus.INVALID,
                MarketSourceReason.OUT_OF_ORDER,
            )
        chronological = chronological[-MAX_MARKET_STATES:]

        timestamps = [state.envelope.occurred_at for state in chronological]
        if len(set(timestamps)) != len(timestamps):
            return self._unavailable(
                observed_at,
                AvailabilityStatus.INVALID,
                MarketSourceReason.DUPLICATE_TIMESTAMPS,
            )
        if any(left >= right for left, right in zip(timestamps, timestamps[1:])):
            return self._unavailable(
                observed_at,
                AvailabilityStatus.INVALID,
                MarketSourceReason.OUT_OF_ORDER,
            )

        source_events = tuple(
            SourceEventIdentity(
                event_id=state.envelope.event_id,
                event_type=state.envelope.event_type,
                source=state.envelope.source,
                schema_version=state.schema_version,
                occurred_at=state.envelope.occurred_at,
                received_at=state.envelope.received_at,
            )
            for state in chronological
        )
        input_identity = MarketInputIdentity(
            economic_instrument=series.economic_instrument,
            market_data_series=series,
            listed_instrument=None,
            timeframe=identity.timeframe,
            strategy_id=identity.strategy_id,
            strategy_version=identity.strategy_version,
            latest_closed_at=chronological[-1].envelope.occurred_at,
            observed_at=observed_at,
            bar_count=len(chronological),
            source_events=source_events,
            source_schema_versions=tuple(
                sorted({state.schema_version for state in chronological})
            ),
        )
        raw_available = MarketSourceAvailability(
            AvailabilityStatus.AVAILABLE, (), observed_at
        )
        if len(chronological) < MAX_MARKET_STATES:
            history_availability = MarketSourceAvailability(
                AvailabilityStatus.INSUFFICIENT_DATA,
                (MarketSourceReason.INSUFFICIENT_HISTORY,),
                observed_at,
            )
        else:
            history_availability = raw_available
        return MarketInputWindow(
            availability=raw_available,
            history_availability=history_availability,
            identity=input_identity,
            states=tuple(chronological),
        )

    @staticmethod
    def _validate_structure(
        rows: list[MarketState], series_symbol: str, observed_at: datetime
    ) -> MarketSourceReason | None:
        for state in rows:
            if not isinstance(state, MarketState):
                return MarketSourceReason.STRUCTURALLY_INVALID
            if state.symbol.ticker != series_symbol:
                return MarketSourceReason.IDENTITY_MISMATCH
            if state.timeframe != Timeframe.M5:
                return MarketSourceReason.TIMEFRAME_MISMATCH
            for timestamp in (
                state.envelope.occurred_at,
                state.envelope.received_at,
            ):
                if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                    return MarketSourceReason.STRUCTURALLY_INVALID
                if timestamp > observed_at + FUTURE_TIMESTAMP_TOLERANCE:
                    return MarketSourceReason.FUTURE_TIMESTAMP
        return None

    @staticmethod
    def _unavailable(
        observed_at: datetime,
        status: AvailabilityStatus,
        reason: MarketSourceReason,
    ) -> MarketInputWindow:
        availability = MarketSourceAvailability(status, (reason,), observed_at)
        return MarketInputWindow(
            availability=availability,
            history_availability=availability,
            identity=None,
        )
