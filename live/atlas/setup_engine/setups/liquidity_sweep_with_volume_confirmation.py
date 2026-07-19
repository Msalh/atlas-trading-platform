"""
Sprint 20. Setup Engine's second real setup - step 1 of Sprint 19's rolling
implementation queue: the lowest-risk possible next setup, mirroring Sprint
18's displacement_with_volume_confirmation pattern exactly, over a different
pair of independent facts.

detected = liquidity_sweep.value AND volume_spike.value - a bar where some
bar in liquidity_sweep's own window breached a reference level and the
current bar's close is back on the origin side, confirmed by volume. The two
facts are independent by construction: liquidity_sweep reads high/low across
its own window plus the four reference levels; volume_spike reads
volume_ratio alone on the current bar - no shared field, no derivation from
one to the other.

Family is ICT (Sprint 19's catalog) - liquidity_sweep is squarely an ICT
liquidity-interaction concept, unlike Sprint 18's MOMENTUM classification.

Unlike displacement_with_volume_confirmation, liquidity_sweep's own evidence
is not already flat: FactResult.evidence["qualifying_levels"] is a LIST of
per-level records, not a scalar - it cannot be passed straight through as
SupportingFact.detail, which is bounded to Mapping[str, int|float|str|bool].
This setup summarizes it instead: qualifying_level_count (an int) and
qualifying_levels (a comma-joined string of level names, built via
tuple(sorted(...)) for a stable canonical order). The sort is applied even
though liquidity_sweep's own list is already produced in a fixed order
internally (_REFERENCE_LEVELS is a tuple, not a set) - this setup's own
determinism should not silently depend on that being true forever, the same
defensive-ordering reasoning raised during this project's earlier review of
a now-superseded sweep/reclaim proposal, applied here for real.
volume_spike's evidence is already flat and is passed straight through
unchanged, the same as Sprint 18.

Severity is fixed at NORMAL for every detected=True result, matching Sprint
18 and the project-wide decision to defer severity calibration until real
data exists.
"""
from atlas.setup_engine.evidence import require_computed_fact, supporting_fact_from_rule_engine_output
from atlas.setup_engine.models import (
    SetupDefinition,
    SetupEvaluationContext,
    SetupEvidence,
    SetupFamily,
    SetupOutcome,
    SetupResult,
    Severity,
)
from atlas.setup_engine.registration import SetupRegistration

DEFAULT_LIQUIDITY_SWEEP_WITH_VOLUME_CONFIRMATION_DEFINITION = SetupDefinition(
    name="liquidity_sweep_with_volume_confirmation",
    version="1.0",
    family=SetupFamily.ICT,
    params={},
)


def evaluate_liquidity_sweep_with_volume_confirmation(
    context: SetupEvaluationContext, definition: SetupDefinition,
) -> SetupOutcome:
    current = context.current
    liquidity_sweep = current.facts["liquidity_sweep"]
    insufficient = require_computed_fact(liquidity_sweep, definition.name, definition.version)
    if insufficient is not None:
        return insufficient

    volume_spike = current.facts["volume_spike"]
    insufficient = require_computed_fact(volume_spike, definition.name, definition.version)
    if insufficient is not None:
        return insufficient

    detected = bool(liquidity_sweep.value) and bool(volume_spike.value)

    qualifying_levels = liquidity_sweep.evidence["qualifying_levels"]
    qualifying_level_names = tuple(sorted(level["reference_level"] for level in qualifying_levels))
    liquidity_sweep_fact = supporting_fact_from_rule_engine_output(
        current, "liquidity_sweep",
        detail={
            "qualifying_level_count": len(qualifying_levels),
            "qualifying_levels": ",".join(qualifying_level_names),
        },
    )
    volume_spike_fact = supporting_fact_from_rule_engine_output(current, "volume_spike", detail=volume_spike.evidence)

    return SetupResult(
        setup_name=definition.name,
        definition_version=definition.version,
        detected=detected,
        severity=Severity.NORMAL if detected else None,
        evidence=SetupEvidence(supporting_facts=(liquidity_sweep_fact, volume_spike_fact)),
    )


LIQUIDITY_SWEEP_WITH_VOLUME_CONFIRMATION_REGISTRATION = SetupRegistration(
    name="liquidity_sweep_with_volume_confirmation",
    evaluate=evaluate_liquidity_sweep_with_volume_confirmation,
    definition=DEFAULT_LIQUIDITY_SWEEP_WITH_VOLUME_CONFIRMATION_DEFINITION,
    required_facts=("liquidity_sweep", "volume_spike"),
)
