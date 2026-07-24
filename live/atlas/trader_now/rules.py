"""Thin composition of the existing canonical Rule Engine service."""

from collections.abc import Callable

from atlas.market_engine.models import MarketState
from atlas.rule_engine.models import RuleEngineOutput
from atlas.rule_engine.service import build_rule_engine_output_window
from atlas.trader_now.models import (
    AvailabilityStatus,
    MarketInputWindow,
    RuleAvailability,
    RuleAvailabilityReason,
    RuleMetadata,
    RuleProjection,
)

RuleWindowEvaluator = Callable[[list[MarketState]], list[RuleEngineOutput]]


class RuleComposer:
    def __init__(
        self,
        evaluator: RuleWindowEvaluator = build_rule_engine_output_window,
    ) -> None:
        self._evaluator = evaluator

    def compose(self, market_input: MarketInputWindow) -> RuleProjection:
        if (
            market_input.availability.status != AvailabilityStatus.AVAILABLE
            or market_input.identity is None
            or not market_input.states
        ):
            return self._unavailable(RuleAvailabilityReason.RAW_MARKET_UNAVAILABLE)

        try:
            outputs = self._evaluator(list(market_input.states))
        except Exception:
            return self._unavailable(RuleAvailabilityReason.RULE_ENGINE_FAILURE)
        if not outputs:
            return self._unavailable(RuleAvailabilityReason.RULE_OUTPUT_UNAVAILABLE)

        output = outputs[-1]
        identity = market_input.identity
        if output.occurred_at != identity.latest_closed_at.isoformat():
            return self._unavailable(RuleAvailabilityReason.TIMESTAMP_MISMATCH)
        if output.symbol != identity.market_data_series.symbol:
            return self._unavailable(RuleAvailabilityReason.IDENTITY_MISMATCH)
        if output.timeframe != identity.timeframe:
            return self._unavailable(RuleAvailabilityReason.TIMEFRAME_MISMATCH)

        return RuleProjection(
            availability=RuleAvailability(AvailabilityStatus.AVAILABLE),
            input_identity=identity,
            output=output,
            metadata=RuleMetadata.from_output(output),
            window=tuple(outputs),
        )

    @staticmethod
    def _unavailable(reason: RuleAvailabilityReason) -> RuleProjection:
        return RuleProjection(
            availability=RuleAvailability(AvailabilityStatus.UNAVAILABLE, (reason,)),
            input_identity=None,
            output=None,
            metadata=None,
        )
