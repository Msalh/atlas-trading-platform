"""
Sprint 17B. Setup Engine's orchestration - a direct generalization of
atlas.rule_engine.service's build_rule_engine_output, one layer up. Pure and
sync, same reasoning: given the same SetupEvaluationContext (and the same
registry), this always returns the same SetupEngineOutput.

evaluate_registration() is split out from build_setup_engine_output()
deliberately, even though today it is a one-line call - it gives future
profiling/tracing exactly one hook point per registration evaluation without
restructuring this module later.

Sprint 24C adds build_setup_engine_output_window() - a direct generalization
of atlas.rule_engine.service.build_rule_engine_output_window, one layer up,
following that function's own shape exactly (see its docstring for the full
reasoning this one reuses rather than re-deriving): given an ordered window
of RuleEngineOutput, return exactly one SetupEngineOutput per input position,
using registry.required_history() bars of trailing history at each position,
however many are actually available so far. This crossed this project's own
"no speculative abstraction" threshold when the Sprint 24B historical
profiler became a real, present consumer needing exactly this capability -
see docs/market_engine/roadmap.md's Sprint 24C entry.
"""
from typing import Any

from atlas.rule_engine.models import RuleEngineOutput
from atlas.setup_engine.models import SetupEngineOutput, SetupEvaluationContext, SetupOutcome, SetupResult
from atlas.setup_engine.registry import REGISTRY, SetupRegistration, required_history

SCHEMA_VERSION = "1.0"


def evaluate_registration(context: SetupEvaluationContext, registration: SetupRegistration) -> SetupOutcome:
    """The single per-registration evaluation point - every setup's outcome
    is produced by calling through here, never by build_setup_engine_output
    calling registration.evaluate directly."""
    return registration.evaluate(context, registration.definition)


def build_setup_engine_output(
    context: SetupEvaluationContext,
    registry: tuple[SetupRegistration, ...] = REGISTRY,
) -> SetupEngineOutput:
    """Pure. Evaluates every registration in `registry`, in registration
    order (deterministic - the same reproducibility Rule Engine's own
    build_rule_engine_output already provides; no setup depends on another's
    output - see Sprint 10's standing registry-ordering rule).
    symbol/timeframe/occurred_at are copied from context.current, never
    re-derived independently."""
    current = context.current
    return SetupEngineOutput(
        schema_version=SCHEMA_VERSION,
        symbol=current.symbol,
        timeframe=current.timeframe,
        occurred_at=current.occurred_at,
        setups=tuple(evaluate_registration(context, r) for r in registry),
    )


def build_setup_engine_output_window(
    rule_engine_output_window: list[RuleEngineOutput],
    registry: tuple[SetupRegistration, ...] = REGISTRY,
) -> list[SetupEngineOutput]:
    """Pure. `rule_engine_output_window` must be chronologically ASCENDING -
    the same convention every window in this codebase already uses. Unlike
    build_rule_engine_output_window, this function does NOT itself validate
    contiguity: a RuleEngineOutput window produced by
    build_rule_engine_output_window is already contiguous by construction
    (it was derived from a single contiguity-validated MarketState window),
    so re-validating here would just be re-checking a property this
    function's only intended construction path already guarantees. A caller
    assembling rule_engine_output_window some other way is responsible for
    that same guarantee - not silently assumed away, just not this
    function's job to re-derive (the same "input selection/segmentation
    stays the caller's responsibility" posture build_rule_engine_output_window
    itself already established one layer down).

    Returns exactly one SetupEngineOutput per input RuleEngineOutput, in the
    same order - never a shorter list, and never suppressing an early
    position. For position i, a SetupEvaluationContext is built from
    rule_engine_output_window[i]'s own preceding history, up to
    registry.required_history() entries, however many are actually available
    within the window so far - the exact same truncation shape
    build_rule_engine_output_window uses for MarketState, one layer up.
    Early positions therefore naturally produce InsufficientData for any
    setup whose required_history exceeds what precedes them (e.g.
    sustained_displacement_streak's required_history=2 cannot resolve at
    position 0, which has no preceding RuleEngineOutput at all) - the same,
    already-existing mechanism SetupEvaluationContext/build_setup_engine_output
    use for any under-length history, not a new concept introduced here. An
    empty rule_engine_output_window produces an empty output list - there is
    no position to ever construct a SetupEvaluationContext for, so its
    __post_init__ empty-history guard is never reached, not bypassed."""
    depth = required_history(registry)
    return [
        build_setup_engine_output(
            SetupEvaluationContext(history=rule_engine_output_window[max(0, i - depth + 1) : i + 1]),
            registry,
        )
        for i in range(len(rule_engine_output_window))
    ]


def _setup_outcome_to_dict(outcome: SetupOutcome) -> dict[str, Any]:
    if isinstance(outcome, SetupResult):
        return {
            "name": outcome.setup_name,
            "status": "computed",
            "detected": outcome.detected,
            "severity": outcome.severity.value if outcome.severity is not None else None,
            "definition_version": outcome.definition_version,
            "evidence": {
                "supporting_facts": [
                    {
                        "fact_name": fact.fact_name,
                        "occurred_at": fact.occurred_at,
                        "value": fact.value,
                        "detail": dict(fact.detail),
                    }
                    for fact in outcome.evidence.supporting_facts
                ],
            },
        }
    return {
        "name": outcome.setup_name,
        "status": "insufficient_data",
        "definition_version": outcome.definition_version,
        "reason": outcome.reason,
    }


def setup_engine_output_to_dict(output: SetupEngineOutput) -> dict[str, Any]:
    """Pure domain serialization - mirrors rule_engine_output_to_dict's own
    posture exactly (no FastAPI/HTTP knowledge). `setups` is already an
    ordered tuple on SetupEngineOutput, so - unlike Rule Engine's own
    facts dict - no dict-to-list transformation happens here; the in-memory
    order and the serialized order are the same object, walked once."""
    return {
        "schema_version": output.schema_version,
        "symbol": output.symbol,
        "timeframe": output.timeframe,
        "occurred_at": output.occurred_at,
        "setups": [_setup_outcome_to_dict(outcome) for outcome in output.setups],
    }
