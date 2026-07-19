"""
Sprint 17B. Setup Engine's orchestration - a direct generalization of
atlas.rule_engine.service's build_rule_engine_output, one layer up. Pure and
sync, same reasoning: given the same SetupEvaluationContext (and the same
registry), this always returns the same SetupEngineOutput.

evaluate_registration() is split out from build_setup_engine_output()
deliberately, even though today it is a one-line call - it gives future
profiling/tracing exactly one hook point per registration evaluation without
restructuring this module later.
"""
from typing import Any

from atlas.setup_engine.models import SetupEngineOutput, SetupEvaluationContext, SetupOutcome, SetupResult
from atlas.setup_engine.registry import REGISTRY, SetupRegistration

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
