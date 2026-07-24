"""Thin composition of the existing canonical Setup Engine service."""

from collections.abc import Callable

from atlas.rule_engine.models import RuleEngineOutput
from atlas.rule_engine.registry import required_history as rule_required_history
from atlas.setup_engine.models import InsufficientData, SetupEngineOutput
from atlas.setup_engine.registry import required_history as setup_required_history
from atlas.setup_engine.service import build_setup_engine_output_window
from atlas.trader_now.models import (
    AvailabilityStatus,
    MarketInputWindow,
    RuleAvailabilityReason,
    RuleProjection,
    SetupAvailability,
    SetupAvailabilityReason,
    SetupAvailabilityStatus,
    SetupMetadata,
    SetupProjection,
)

SetupWindowEvaluator = Callable[[list[RuleEngineOutput]], list[SetupEngineOutput]]


def combined_rule_setup_history_required() -> int:
    """Derive the existing live minimum from the two canonical registries."""
    return rule_required_history() + setup_required_history() - 1


class SetupComposer:
    def __init__(
        self,
        evaluator: SetupWindowEvaluator = build_setup_engine_output_window,
    ) -> None:
        self._evaluator = evaluator

    def compose(
        self,
        *,
        market_input: MarketInputWindow,
        rules: RuleProjection,
    ) -> SetupProjection:
        if (
            market_input.availability.status != AvailabilityStatus.AVAILABLE
            or market_input.identity is None
        ):
            return self._dependency_unavailable(
                SetupAvailabilityReason.RAW_INPUT_UNAVAILABLE,
                rules.availability.reason_codes,
            )
        if rules.availability.status != AvailabilityStatus.AVAILABLE:
            rule_alignment_reasons = {
                RuleAvailabilityReason.TIMESTAMP_MISMATCH,
                RuleAvailabilityReason.IDENTITY_MISMATCH,
                RuleAvailabilityReason.TIMEFRAME_MISMATCH,
            }
            reason = (
                SetupAvailabilityReason.RULE_ALIGNMENT_INVALID
                if any(
                    entry in rule_alignment_reasons
                    for entry in rules.availability.reason_codes
                )
                else SetupAvailabilityReason.RULE_OUTPUT_UNAVAILABLE
            )
            return self._dependency_unavailable(reason, rules.availability.reason_codes)
        if (
            rules.input_identity != market_input.identity
            or not rules.window
            or rules.output is None
            or rules.window[-1] is not rules.output
        ):
            return self._dependency_unavailable(
                SetupAvailabilityReason.RULE_ALIGNMENT_INVALID,
                (RuleAvailabilityReason.IDENTITY_MISMATCH,),
            )

        identity = market_input.identity
        latest_rule = rules.output
        if (
            latest_rule.occurred_at != identity.latest_closed_at.isoformat()
            or latest_rule.symbol != identity.market_data_series.symbol
            or latest_rule.timeframe != identity.timeframe
        ):
            return self._dependency_unavailable(
                SetupAvailabilityReason.RULE_ALIGNMENT_INVALID,
                (RuleAvailabilityReason.TIMESTAMP_MISMATCH,),
            )

        try:
            outputs = self._evaluator(list(rules.window))
        except Exception:
            return self._unavailable(
                SetupAvailabilityStatus.UNAVAILABLE,
                SetupAvailabilityReason.SETUP_ENGINE_FAILURE,
            )
        if not outputs:
            return self._unavailable(
                SetupAvailabilityStatus.UNAVAILABLE,
                SetupAvailabilityReason.EMPTY_SETUP_OUTPUT,
            )
        output = outputs[-1]
        if not isinstance(output, SetupEngineOutput) or not output.setups:
            return self._unavailable(
                SetupAvailabilityStatus.INVALID,
                SetupAvailabilityReason.STRUCTURALLY_INVALID,
            )

        reasons: list[SetupAvailabilityReason] = []
        if output.occurred_at != identity.latest_closed_at.isoformat():
            reasons.append(SetupAvailabilityReason.TIMESTAMP_MISMATCH)
        if output.occurred_at != latest_rule.occurred_at:
            reasons.append(SetupAvailabilityReason.SETUP_TO_RULE_TIMESTAMP_MISMATCH)
        if output.symbol != identity.market_data_series.symbol:
            reasons.append(SetupAvailabilityReason.SYMBOL_MISMATCH)
        if output.timeframe != identity.timeframe:
            reasons.append(SetupAvailabilityReason.TIMEFRAME_MISMATCH)
        if reasons:
            return SetupProjection(
                availability=SetupAvailability(
                    SetupAvailabilityStatus.INVALID, tuple(reasons)
                ),
                input_identity=None,
                output=None,
                metadata=None,
            )

        has_insufficient = any(
            isinstance(outcome, InsufficientData) for outcome in output.setups
        )
        insufficient_history = (
            len(market_input.states) < combined_rule_setup_history_required()
        )
        if has_insufficient or insufficient_history:
            availability = SetupAvailability(
                SetupAvailabilityStatus.INSUFFICIENT_DATA,
                (SetupAvailabilityReason.INSUFFICIENT_HISTORY,),
            )
        else:
            availability = SetupAvailability(SetupAvailabilityStatus.AVAILABLE)
        return SetupProjection(
            availability=availability,
            input_identity=identity,
            output=output,
            metadata=SetupMetadata.from_output(output, rules.window),
            window=tuple(outputs),
        )

    @staticmethod
    def _dependency_unavailable(
        reason: SetupAvailabilityReason,
        rule_reasons: tuple[RuleAvailabilityReason, ...],
    ) -> SetupProjection:
        return SetupProjection(
            availability=SetupAvailability(
                SetupAvailabilityStatus.UNAVAILABLE_DUE_TO_DEPENDENCY,
                (reason,),
                rule_reasons,
            ),
            input_identity=None,
            output=None,
            metadata=None,
        )

    @staticmethod
    def _unavailable(
        status: SetupAvailabilityStatus,
        reason: SetupAvailabilityReason,
    ) -> SetupProjection:
        return SetupProjection(
            availability=SetupAvailability(status, (reason,)),
            input_identity=None,
            output=None,
            metadata=None,
        )
