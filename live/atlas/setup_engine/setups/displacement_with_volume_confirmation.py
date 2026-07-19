"""
Sprint 18. Setup Engine's first real setup - a deliberately minimal vertical
slice proving the Sprint 17B foundation (SetupEvaluationContext, evidence,
severity, registry, serialization, orchestration) against real deterministic
logic, chosen specifically to minimize domain controversy: the setup's name,
required facts, logic, and evidence all describe exactly the same
computation, nothing more.

detected = displacement.value AND volume_spike.value - a bar whose range
relative to ATR exceeds displacement's own threshold, and whose volume
relative to its baseline exceeds volume_spike's own threshold, on the same
bar. The two facts are independent by construction (displacement reads
high/low/atr; volume_spike reads volume_ratio alone - no shared field, no
derivation from one to the other), so this composition adds genuine
information beyond either fact alone, unlike this Sprint's earlier,
rejected proposals.

Both required facts return a single scalar bool with an already-flat
evidence dict (no per-reference-level list, unlike rejection/liquidity_sweep/
reclaim) - so there is no qualifying-level set to intersect, no coincident
price level to deduplicate, and no ordering concern to guard against. Each
fact's own `evidence` dict is passed straight through as SupportingFact.detail
rather than re-keyed field by field - it is already exactly
Mapping[str, int|float|str|bool], and re-typing the same two field names here
would only risk drifting from facts.py's own field names over time.

Family is MOMENTUM, not ORDER_FLOW - this setup uses no bid/ask, delta,
footprint, imbalance, or absorption data, so ORDER_FLOW would have diluted
that family's meaning before any real order-flow setup exists (see
SetupFamily's own docstring).

Severity is fixed at NORMAL for every detected=True result - no tiering.
Calibrating a real severity metric is deliberately left to a future Sprint,
once real data exists to calibrate against, not invented here.
"""
from atlas.rule_engine.models import FactOutcome
from atlas.rule_engine.models import InsufficientData as FactInsufficientData
from atlas.setup_engine.evidence import supporting_fact_from_rule_engine_output
from atlas.setup_engine.models import (
    InsufficientData,
    SetupDefinition,
    SetupEvaluationContext,
    SetupEvidence,
    SetupFamily,
    SetupOutcome,
    SetupResult,
    Severity,
)
from atlas.setup_engine.registration import SetupRegistration

DEFAULT_DISPLACEMENT_WITH_VOLUME_CONFIRMATION_DEFINITION = SetupDefinition(
    name="displacement_with_volume_confirmation",
    version="1.0",
    family=SetupFamily.MOMENTUM,
    params={},
)


def _require_computed(outcome: FactOutcome, setup_name: str, definition_version: str):
    if isinstance(outcome, FactInsufficientData):
        return InsufficientData(
            setup_name=setup_name, definition_version=definition_version,
            reason=f"{outcome.fact_name} is insufficient_data: {outcome.reason}",
        )
    return None


def evaluate_displacement_with_volume_confirmation(
    context: SetupEvaluationContext, definition: SetupDefinition,
) -> SetupOutcome:
    current = context.current
    displacement = current.facts["displacement"]
    insufficient = _require_computed(displacement, definition.name, definition.version)
    if insufficient is not None:
        return insufficient

    volume_spike = current.facts["volume_spike"]
    insufficient = _require_computed(volume_spike, definition.name, definition.version)
    if insufficient is not None:
        return insufficient

    detected = bool(displacement.value) and bool(volume_spike.value)

    displacement_fact = supporting_fact_from_rule_engine_output(current, "displacement", detail=displacement.evidence)
    volume_spike_fact = supporting_fact_from_rule_engine_output(current, "volume_spike", detail=volume_spike.evidence)

    return SetupResult(
        setup_name=definition.name,
        definition_version=definition.version,
        detected=detected,
        severity=Severity.NORMAL if detected else None,
        evidence=SetupEvidence(supporting_facts=(displacement_fact, volume_spike_fact)),
    )


DISPLACEMENT_WITH_VOLUME_CONFIRMATION_REGISTRATION = SetupRegistration(
    name="displacement_with_volume_confirmation",
    evaluate=evaluate_displacement_with_volume_confirmation,
    definition=DEFAULT_DISPLACEMENT_WITH_VOLUME_CONFIRMATION_DEFINITION,
    required_facts=("displacement", "volume_spike"),
)
