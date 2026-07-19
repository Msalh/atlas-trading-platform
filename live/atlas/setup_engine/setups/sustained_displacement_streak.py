"""
Sprint 21. Setup Engine's third real setup - the first requiring
required_history > 1, and the first to genuinely use context.history beyond
context.current: detects two or more CONSECUTIVE RuleEngineOutput entries,
ending at the current bar, that each independently satisfy displacement=True.

min_streak_length (definition.params, default 2) is the detection
threshold, not a hard cap on how much history is examined - see below for
why this differs from Rule Engine's own windowed facts. required_history
(derived via history_param="min_streak_length", the same
never-a-second-stored-copy discipline FactRegistration.window_param and
Sprint 18/20's own SetupRegistration.history_param already established) is
therefore the MINIMUM bars needed to ever detect at all, not the number
this setup actually reads: given more history than the minimum, this setup
walks backward from the current bar through as much of context.history as
forms an unbroken run of displacement=True, and reports the real streak
length. It does not truncate to exactly required_history the way Rule
Engine's fixed-window facts (trend_5m, liquidity_sweep, reclaim) truncate
to exactly their configured window. That truncating behavior is correct for
those facts because their formulas are defined over an exact N-bar window
(an OLS slope over a different N would mean something different); "how
long is the current streak" has no such fixed-N definition - it is
inherently open-ended, so examining all available history and reporting
the true length is the correct modeling choice here, not a shortcut.

Walking stops at the first bar (working backward from current) whose
displacement is False OR insufficient_data - an insufficient bar breaks the
streak the same way a False bar does, rather than propagating insufficiency
for the whole setup. Deliberate: an unconfirmable OLDER bar genuinely
cannot corroborate a streak, the same way a confirmed-False bar cannot -
both mean "the streak's requirement of independently verified True bars is
not satisfied at that position." The CURRENT bar is treated differently: if
displacement is insufficient_data on context.current itself, this setup
returns InsufficientData rather than a false-flavored SetupResult, because
no meaningful streak conclusion (including "not detected") can be drawn
about right now without knowing what's true right now.

Evidence carries one SupportingFact per bar actually in the streak (zero
when the current bar itself doesn't qualify - a variable-length evidence
tuple, unlike Sprint 18/20's fixed-two-entries shape, which was simply a
consequence of those setups always checking exactly two facts; there is no
general Setup Engine rule requiring a fixed evidence count). Chronological
order (oldest first, current last - the convention every window in this
codebase already uses). Each entry carries that bar's own displacement
evidence plus the computed streak_length - a scalar, so it fits
SupportingFact.detail's existing bounded type without any Setup Engine
model change.

Family is MOMENTUM, matching displacement_with_volume_confirmation's own
classification (Sprint 19's catalog). Severity is fixed at NORMAL for every
detected=True result, matching every other setup built so far.
"""
from atlas.rule_engine.models import RuleEngineOutput
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

DEFAULT_SUSTAINED_DISPLACEMENT_STREAK_DEFINITION = SetupDefinition(
    name="sustained_displacement_streak",
    version="1.0",
    family=SetupFamily.MOMENTUM,
    params={"min_streak_length": 2},
)


def evaluate_sustained_displacement_streak(
    context: SetupEvaluationContext, definition: SetupDefinition,
) -> SetupOutcome:
    min_streak_length = definition.params["min_streak_length"]

    if len(context.history) < min_streak_length:
        return InsufficientData(
            setup_name=definition.name, definition_version=definition.version,
            reason=f"fewer than {min_streak_length} bars available in history (got {len(context.history)})",
        )

    current_displacement = context.current.facts["displacement"]
    if isinstance(current_displacement, FactInsufficientData):
        return InsufficientData(
            setup_name=definition.name, definition_version=definition.version,
            reason=f"displacement is insufficient_data on the current bar: {current_displacement.reason}",
        )

    streak: list[RuleEngineOutput] = []
    for output in reversed(context.history):
        displacement = output.facts["displacement"]
        if isinstance(displacement, FactInsufficientData) or displacement.value is not True:
            break
        streak.append(output)

    streak.reverse()  # chronological order, oldest first, current last
    streak_length = len(streak)
    detected = streak_length >= min_streak_length

    supporting_facts = tuple(
        supporting_fact_from_rule_engine_output(
            output, "displacement",
            detail={**output.facts["displacement"].evidence, "streak_length": streak_length},
        )
        for output in streak
    )

    return SetupResult(
        setup_name=definition.name,
        definition_version=definition.version,
        detected=detected,
        severity=Severity.NORMAL if detected else None,
        evidence=SetupEvidence(supporting_facts=supporting_facts),
    )


SUSTAINED_DISPLACEMENT_STREAK_REGISTRATION = SetupRegistration(
    name="sustained_displacement_streak",
    evaluate=evaluate_sustained_displacement_streak,
    definition=DEFAULT_SUSTAINED_DISPLACEMENT_STREAK_DEFINITION,
    history_param="min_streak_length",
    required_facts=("displacement",),
)
