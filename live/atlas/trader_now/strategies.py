"""Replay-equivalent composition of the canonical Strategy Engine."""

from collections.abc import Sequence
from typing import Protocol

from atlas.replay_engine.models import ReplayFrame
from atlas.strategy_engine.models import (
    StrategyDecision,
    StrategyDirection,
    StrategyDisposition,
)
from atlas.strategy_engine.ports import StrategyPlugin
from atlas.strategy_engine.service import (
    StrategyContextFingerprintMismatchError,
    StrategyIdentityMismatchError,
    StrategyOccurredAtMismatchError,
    evaluate_strategies,
)
from atlas.strategy_engine.strategies.displacement_volume_context import (
    DisplacementVolumeContext,
)
from atlas.trader_now.models import (
    AvailabilityStatus,
    ContextAvailabilityReason,
    ContextAvailabilityStatus,
    ContextProjection,
    InterpretationAvailabilityReason,
    InterpretationAvailabilityStatus,
    InterpretationProjection,
    MarketInputWindow,
    MarketSourceReason,
    RuleAvailabilityReason,
    RuleProjection,
    SetupAvailabilityReason,
    SetupAvailabilityStatus,
    SetupProjection,
    StrategyAvailability,
    StrategyAvailabilityReason,
    StrategyAvailabilityStatus,
    StrategyMetadata,
    StrategyProjection,
)


class StrategyEvaluator(Protocol):
    def __call__(
        self,
        frame: ReplayFrame,
        strategies: Sequence[StrategyPlugin],
    ) -> tuple[StrategyDecision, ...]: ...


class StrategyComposer:
    """Build one canonical frame and evaluate the configured plugin sequence."""

    def __init__(
        self,
        *,
        evaluator: StrategyEvaluator = evaluate_strategies,
        strategies: Sequence[StrategyPlugin] | None = None,
    ) -> None:
        self._evaluator = evaluator
        self._strategies = tuple(
            strategies if strategies is not None else (DisplacementVolumeContext(),)
        )

    def compose(
        self,
        *,
        market_input: MarketInputWindow,
        rules: RuleProjection,
        setups: SetupProjection,
        context: ContextProjection,
        interpretations: InterpretationProjection,
    ) -> StrategyProjection:
        dependency_failure = self._dependency_failure(
            market_input=market_input,
            rules=rules,
            setups=setups,
            context=context,
            interpretations=interpretations,
        )
        if dependency_failure is not None:
            return dependency_failure

        identity = market_input.identity
        rule_output = rules.output
        setup_output = setups.output
        context_output = context.output
        assert identity is not None
        assert rule_output is not None
        assert setup_output is not None
        assert context_output is not None

        expected_at = identity.latest_closed_at
        if (
            market_input.states[-1].envelope.occurred_at != expected_at
            or rule_output.occurred_at != expected_at.isoformat()
            or setup_output.occurred_at != expected_at.isoformat()
            or any(entry.occurred_at != expected_at for entry in interpretations.output)
        ):
            return self._invalid(
                StrategyAvailabilityReason.DEPENDENCY_ALIGNMENT_INVALID
            )
        if context_output.occurred_at != expected_at:
            return self._invalid(StrategyAvailabilityReason.CONTEXT_TIMESTAMP_MISMATCH)

        expected_symbol = identity.market_data_series.symbol
        source_symbols = (
            market_input.states[-1].symbol.ticker,
            rule_output.symbol,
            setup_output.symbol,
            context_output.symbol.ticker,
        )
        if any(symbol != expected_symbol for symbol in source_symbols):
            return self._invalid(StrategyAvailabilityReason.SYMBOL_MISMATCH)
        source_timeframes = (
            market_input.states[-1].timeframe.value,
            rule_output.timeframe,
            setup_output.timeframe,
            context_output.timeframe.value,
        )
        if any(value != identity.timeframe for value in source_timeframes):
            return self._invalid(StrategyAvailabilityReason.TIMEFRAME_MISMATCH)

        setup_ids = tuple(outcome.setup_name for outcome in setup_output.setups)
        interpretation_ids = tuple(entry.setup_id for entry in interpretations.output)
        if len(set(setup_ids)) != len(setup_ids):
            return self._invalid(StrategyAvailabilityReason.DUPLICATE_SETUP_IDENTITY)
        if len(set(interpretation_ids)) != len(interpretation_ids):
            return self._invalid(
                StrategyAvailabilityReason.AMBIGUOUS_INTERPRETATION_MAPPING
            )
        if setup_ids != interpretation_ids:
            return self._invalid(
                StrategyAvailabilityReason.INTERPRETATION_IDENTITY_MISMATCH
            )

        if (
            rules.metadata is None
            or rules.metadata.symbol != rule_output.symbol
            or rules.metadata.timeframe != rule_output.timeframe
            or rules.metadata.occurred_at != rule_output.occurred_at
            or setups.metadata is None
            or setups.metadata.symbol != setup_output.symbol
            or setups.metadata.timeframe != setup_output.timeframe
            or setups.metadata.occurred_at != setup_output.occurred_at
        ):
            return self._invalid(
                StrategyAvailabilityReason.DEPENDENCY_ALIGNMENT_INVALID
            )
        if (
            context.metadata is None
            or context.metadata.context_fingerprint
            != context_output.context_fingerprint
        ):
            return self._invalid(
                StrategyAvailabilityReason.CONTEXT_FINGERPRINT_MISMATCH
            )
        if context.metadata.quality != context_output.quality:
            return self._invalid(StrategyAvailabilityReason.CONTEXT_QUALITY_MISMATCH)
        expected_interpretation_versions = tuple(
            sorted({entry.interpretation_version for entry in interpretations.output})
        )
        expected_interpretation_fingerprints = tuple(
            sorted(
                {entry.interpretation_fingerprint for entry in interpretations.output}
            )
        )
        if (
            interpretations.metadata is None
            or interpretations.metadata.setup_ids != interpretation_ids
            or interpretations.metadata.occurred_at != expected_at
            or interpretations.metadata.source_identity.symbol != expected_symbol
            or interpretations.metadata.source_identity.timeframe != identity.timeframe
            or interpretations.metadata.source_identity.occurred_at
            != expected_at.isoformat()
            or interpretations.metadata.interpretation_versions
            != expected_interpretation_versions
            or interpretations.metadata.interpretation_fingerprints
            != expected_interpretation_fingerprints
        ):
            return self._invalid(
                StrategyAvailabilityReason.INTERPRETATION_IDENTITY_MISMATCH
            )
        if any(
            plugin.strategy_id != identity.strategy_id for plugin in self._strategies
        ) or any(
            plugin.strategy_version != identity.strategy_version
            for plugin in self._strategies
        ):
            return self._invalid(StrategyAvailabilityReason.STRATEGY_IDENTITY_MISMATCH)

        frame = ReplayFrame(
            market_state=market_input.states[-1],
            rule_engine_output=rule_output,
            setup_engine_output=setup_output,
            market_context=context_output,
            setup_interpretations=interpretations.output,
        )
        try:
            output = self._evaluator(frame, self._strategies)
        except StrategyOccurredAtMismatchError:
            return self._invalid(StrategyAvailabilityReason.TIMESTAMP_MISMATCH)
        except StrategyContextFingerprintMismatchError:
            return self._invalid(
                StrategyAvailabilityReason.CONTEXT_FINGERPRINT_MISMATCH
            )
        except StrategyIdentityMismatchError:
            return self._invalid(StrategyAvailabilityReason.STRATEGY_IDENTITY_MISMATCH)
        except Exception:  # noqa: BLE001 - section availability owns service failures
            return self._without_output(
                StrategyAvailabilityStatus.UNAVAILABLE,
                StrategyAvailabilityReason.SERVICE_FAILURE,
            )
        if not output:
            return self._without_output(
                StrategyAvailabilityStatus.UNAVAILABLE,
                StrategyAvailabilityReason.EMPTY_OUTPUT,
            )
        if not isinstance(output, tuple) or any(
            not isinstance(entry, StrategyDecision) for entry in output
        ):
            return self._invalid(StrategyAvailabilityReason.STRUCTURALLY_INVALID)

        reasons: list[StrategyAvailabilityReason] = []
        if any(entry.occurred_at != expected_at for entry in output):
            reasons.append(StrategyAvailabilityReason.TIMESTAMP_MISMATCH)
        if any(
            entry.context_fingerprint != context_output.context_fingerprint
            for entry in output
        ):
            reasons.append(StrategyAvailabilityReason.CONTEXT_FINGERPRINT_MISMATCH)
        plugin_identity = tuple(
            (plugin.strategy_id, plugin.strategy_version) for plugin in self._strategies
        )
        decision_identity = tuple(
            (entry.strategy_id, entry.strategy_version) for entry in output
        )
        if decision_identity != plugin_identity:
            reasons.append(StrategyAvailabilityReason.STRATEGY_IDENTITY_MISMATCH)
        if any(
            not isinstance(entry.disposition, StrategyDisposition) for entry in output
        ):
            reasons.append(StrategyAvailabilityReason.UNSUPPORTED_DISPOSITION)
        if any(not isinstance(entry.direction, StrategyDirection) for entry in output):
            reasons.append(StrategyAvailabilityReason.UNSUPPORTED_DIRECTION)
        if any(
            entry.occurred_at.tzinfo is None
            or entry.occurred_at.utcoffset() is None
            or not entry.strategy_id
            or not entry.strategy_version
            or not entry.context_fingerprint
            for entry in output
        ):
            reasons.append(StrategyAvailabilityReason.STRUCTURALLY_INVALID)
        if reasons:
            return self._invalid(*tuple(dict.fromkeys(reasons)))

        setup_versions = {
            outcome.setup_name: outcome.definition_version
            for outcome in setup_output.setups
        }
        interpretation_versions = {
            entry.setup_id: entry.interpretation_version
            for entry in interpretations.output
        }
        interpretation_fingerprints = {
            entry.setup_id: entry.interpretation_fingerprint
            for entry in interpretations.output
        }
        return StrategyProjection(
            availability=StrategyAvailability(StrategyAvailabilityStatus.AVAILABLE),
            input_identity=identity,
            output=output,
            metadata=StrategyMetadata(
                occurred_at=expected_at,
                strategy_versions={
                    entry.strategy_id: entry.strategy_version for entry in output
                },
                dispositions={entry.strategy_id: entry.disposition for entry in output},
                directions={entry.strategy_id: entry.direction for entry in output},
                reason_codes={
                    entry.strategy_id: entry.reason_codes for entry in output
                },
                context_fingerprint=context_output.context_fingerprint,
                context_quality=context_output.quality,
                source_symbol=expected_symbol,
                source_timeframe=identity.timeframe,
                setup_definition_versions=setup_versions,
                interpretation_versions=interpretation_versions,
                interpretation_fingerprints=interpretation_fingerprints,
            ),
        )

    @staticmethod
    def _dependency_failure(
        *,
        market_input: MarketInputWindow,
        rules: RuleProjection,
        setups: SetupProjection,
        context: ContextProjection,
        interpretations: InterpretationProjection,
    ) -> StrategyProjection | None:
        if (
            market_input.availability.status != AvailabilityStatus.AVAILABLE
            or market_input.identity is None
            or not market_input.states
        ):
            return StrategyComposer._dependency_unavailable(
                StrategyAvailabilityReason.RAW_INPUT_UNAVAILABLE,
                market_reasons=market_input.availability.reason_codes,
            )
        if (
            rules.availability.status != AvailabilityStatus.AVAILABLE
            or rules.input_identity is None
            or rules.output is None
        ):
            return StrategyComposer._dependency_unavailable(
                StrategyAvailabilityReason.RULE_DEPENDENCY_UNAVAILABLE,
                rule_reasons=rules.availability.reason_codes,
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
            return StrategyComposer._dependency_unavailable(
                StrategyAvailabilityReason.SETUP_DEPENDENCY_UNAVAILABLE,
                setup_reasons=setups.availability.reason_codes,
            )
        if (
            context.availability.status
            not in (
                ContextAvailabilityStatus.AVAILABLE,
                ContextAvailabilityStatus.INSUFFICIENT_DATA,
            )
            or context.input_identity is None
            or context.output is None
        ):
            return StrategyComposer._dependency_unavailable(
                StrategyAvailabilityReason.CONTEXT_DEPENDENCY_UNAVAILABLE,
                context_reasons=context.availability.reason_codes,
            )
        if (
            interpretations.availability.status
            != InterpretationAvailabilityStatus.AVAILABLE
            or interpretations.input_identity is None
            or not interpretations.output
        ):
            return StrategyComposer._dependency_unavailable(
                StrategyAvailabilityReason.INTERPRETATION_DEPENDENCY_UNAVAILABLE,
                interpretation_reasons=interpretations.availability.reason_codes,
            )
        identities = (
            market_input.identity,
            rules.input_identity,
            setups.input_identity,
            context.input_identity,
            interpretations.input_identity,
        )
        if any(value != market_input.identity for value in identities):
            return StrategyComposer._dependency_unavailable(
                StrategyAvailabilityReason.DEPENDENCY_ALIGNMENT_INVALID
            )
        return None

    @staticmethod
    def _dependency_unavailable(
        reason: StrategyAvailabilityReason,
        *,
        market_reasons: tuple[MarketSourceReason, ...] = (),
        rule_reasons: tuple[RuleAvailabilityReason, ...] = (),
        setup_reasons: tuple[SetupAvailabilityReason, ...] = (),
        context_reasons: tuple[ContextAvailabilityReason, ...] = (),
        interpretation_reasons: tuple[InterpretationAvailabilityReason, ...] = (),
    ) -> StrategyProjection:
        return StrategyProjection(
            availability=StrategyAvailability(
                StrategyAvailabilityStatus.UNAVAILABLE_DUE_TO_DEPENDENCY,
                (reason,),
                market_reasons,
                rule_reasons,
                setup_reasons,
                context_reasons,
                interpretation_reasons,
            ),
            input_identity=None,
            output=(),
            metadata=None,
        )

    @staticmethod
    def _invalid(
        *reasons: StrategyAvailabilityReason,
    ) -> StrategyProjection:
        return StrategyComposer._without_output(
            StrategyAvailabilityStatus.INVALID, *reasons
        )

    @staticmethod
    def _without_output(
        status: StrategyAvailabilityStatus,
        *reasons: StrategyAvailabilityReason,
    ) -> StrategyProjection:
        return StrategyProjection(
            availability=StrategyAvailability(status, reasons),
            input_identity=None,
            output=(),
            metadata=None,
        )
