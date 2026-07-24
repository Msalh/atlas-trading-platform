"""Thin composition of the canonical Setup Interpretation public service."""

from typing import Protocol

from atlas.rule_engine.models import RuleEngineOutput
from atlas.setup_engine.models import SetupEngineOutput
from atlas.setup_interpretation.models import (
    DirectionSource,
    SetupDirection,
    SetupInterpretation,
)
from atlas.setup_interpretation.service import interpret_setups
from atlas.trader_now.models import (
    AvailabilityStatus,
    InterpretationAvailability,
    InterpretationAvailabilityReason,
    InterpretationAvailabilityStatus,
    InterpretationMetadata,
    InterpretationProjection,
    RuleAvailabilityReason,
    RuleProjection,
    SetupAvailabilityReason,
    SetupAvailabilityStatus,
    SetupProjection,
)


class InterpretationEvaluator(Protocol):
    def __call__(
        self,
        *,
        rule_engine_output: RuleEngineOutput,
        setup_engine_output: SetupEngineOutput,
    ) -> tuple[SetupInterpretation, ...]: ...


class SetupInterpretationComposer:
    """Adapt aligned Rule/Setup projections to canonical interpretation."""

    def __init__(
        self,
        evaluator: InterpretationEvaluator = interpret_setups,
    ) -> None:
        self._evaluator = evaluator

    def compose(
        self,
        *,
        rules: RuleProjection,
        setups: SetupProjection,
    ) -> InterpretationProjection:
        if (
            rules.availability.status != AvailabilityStatus.AVAILABLE
            or rules.input_identity is None
            or rules.output is None
        ):
            return self._dependency_unavailable(
                InterpretationAvailabilityReason.RULE_DEPENDENCY_UNAVAILABLE,
                rules.availability.reason_codes,
                (),
            )
        if (
            setups.availability.status
            not in (
                SetupAvailabilityStatus.AVAILABLE,
                SetupAvailabilityStatus.INSUFFICIENT_DATA,
            )
            or setups.input_identity is None
            or setups.output is None
        ):
            return self._dependency_unavailable(
                InterpretationAvailabilityReason.SETUP_DEPENDENCY_UNAVAILABLE,
                (),
                setups.availability.reason_codes,
            )

        rule_output = rules.output
        setup_output = setups.output
        identity = rules.input_identity
        dependency_structurally_aligned = (
            setups.input_identity == identity
            and bool(rules.window)
            and rules.window[-1] is rule_output
            and bool(setups.window)
            and setups.window[-1] is setup_output
        )
        if not dependency_structurally_aligned:
            return self._dependency_unavailable(
                InterpretationAvailabilityReason.DEPENDENCY_ALIGNMENT_INVALID,
                (),
                (),
            )
        if (
            rule_output.occurred_at != setup_output.occurred_at
            or rule_output.occurred_at != identity.latest_closed_at.isoformat()
        ):
            return self._without_output(
                InterpretationAvailabilityStatus.INVALID,
                InterpretationAvailabilityReason.SOURCE_TIMESTAMP_MISMATCH,
            )
        if (
            rule_output.symbol != setup_output.symbol
            or rule_output.symbol != identity.market_data_series.symbol
        ):
            return self._without_output(
                InterpretationAvailabilityStatus.INVALID,
                InterpretationAvailabilityReason.SOURCE_SYMBOL_MISMATCH,
            )
        if (
            rule_output.timeframe != setup_output.timeframe
            or rule_output.timeframe != identity.timeframe
        ):
            return self._without_output(
                InterpretationAvailabilityStatus.INVALID,
                InterpretationAvailabilityReason.SOURCE_TIMEFRAME_MISMATCH,
            )

        try:
            output = self._evaluator(
                rule_engine_output=rule_output,
                setup_engine_output=setup_output,
            )
        except Exception:  # noqa: BLE001 - section availability owns service failures
            return self._without_output(
                InterpretationAvailabilityStatus.UNAVAILABLE,
                InterpretationAvailabilityReason.SERVICE_FAILURE,
            )
        if not output:
            return self._without_output(
                InterpretationAvailabilityStatus.UNAVAILABLE,
                InterpretationAvailabilityReason.EMPTY_OUTPUT,
            )
        if not isinstance(output, tuple) or any(
            not isinstance(entry, SetupInterpretation) for entry in output
        ):
            return self._without_output(
                InterpretationAvailabilityStatus.INVALID,
                InterpretationAvailabilityReason.STRUCTURALLY_INVALID,
            )

        reasons: list[InterpretationAvailabilityReason] = []
        expected_at = identity.latest_closed_at
        if any(entry.occurred_at != expected_at for entry in output):
            reasons.append(InterpretationAvailabilityReason.TIMESTAMP_MISMATCH)
        if any(
            entry.occurred_at.tzinfo is None
            or entry.occurred_at.utcoffset() is None
            or not entry.setup_id
            or not entry.interpretation_version
            or not entry.interpretation_fingerprint
            for entry in output
        ):
            reasons.append(InterpretationAvailabilityReason.STRUCTURALLY_INVALID)
        if any(not isinstance(entry.direction, SetupDirection) for entry in output):
            reasons.append(InterpretationAvailabilityReason.UNSUPPORTED_DIRECTION)
        if any(not isinstance(entry.source, DirectionSource) for entry in output):
            reasons.append(InterpretationAvailabilityReason.UNSUPPORTED_SOURCE)
        if len(output) != len(setup_output.setups) or tuple(
            entry.setup_id for entry in output
        ) != tuple(entry.setup_name for entry in setup_output.setups):
            reasons.append(InterpretationAvailabilityReason.STRUCTURALLY_INVALID)
        if reasons:
            return InterpretationProjection(
                availability=InterpretationAvailability(
                    InterpretationAvailabilityStatus.INVALID,
                    tuple(dict.fromkeys(reasons)),
                ),
                input_identity=None,
                output=(),
                metadata=None,
            )

        return InterpretationProjection(
            availability=InterpretationAvailability(
                InterpretationAvailabilityStatus.AVAILABLE
            ),
            input_identity=identity,
            output=output,
            metadata=InterpretationMetadata.from_output(
                output, rule_output, setup_output
            ),
        )

    @staticmethod
    def _dependency_unavailable(
        reason: InterpretationAvailabilityReason,
        rule_reasons: tuple[RuleAvailabilityReason, ...],
        setup_reasons: tuple[SetupAvailabilityReason, ...],
    ) -> InterpretationProjection:
        return InterpretationProjection(
            availability=InterpretationAvailability(
                InterpretationAvailabilityStatus.UNAVAILABLE_DUE_TO_DEPENDENCY,
                (reason,),
                rule_reasons,
                setup_reasons,
            ),
            input_identity=None,
            output=(),
            metadata=None,
        )

    @staticmethod
    def _without_output(
        status: InterpretationAvailabilityStatus,
        reason: InterpretationAvailabilityReason,
    ) -> InterpretationProjection:
        return InterpretationProjection(
            availability=InterpretationAvailability(status, (reason,)),
            input_identity=None,
            output=(),
            metadata=None,
        )
