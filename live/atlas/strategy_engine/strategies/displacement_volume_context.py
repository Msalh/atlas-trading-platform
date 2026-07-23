"""
DisplacementVolumeContext - Phase N3, Sprint 3; migrated Sprint 6 (Setup
Interpretation integration) to consume the certified SetupInterpretation
already present on ReplayFrame.setup_interpretations (Replay Engine
Sprint 5) instead of reading Rule Engine facts directly.

Recomputes nothing: every input this plugin reads is an already-computed,
already-typed field on the ReplayFrame it is given -
frame.setup_engine_output.setups (the "displacement_with_volume_confirmation"
SetupOutcome), frame.setup_interpretations (the matching
SetupInterpretation - Setup Interpretation's own canonical direction for
that same setup), and frame.market_context.quality (Market Context's own
three-state ContextQuality). No OHLC is read directly; no displacement/
volume/trend value is recalculated, and interpret_setups() is never
called from here - Replay Engine already called it once, and this plugin
only reads what it produced.

--- Sprint 6 migration: what changed, what didn't ---

Sprint 3's disclosed, narrow widening of Strategy Engine's dependency
ceiling (importing exactly atlas.rule_engine.models.FactResult, nothing
else) is fully removed by this migration - this module no longer imports
anything from atlas.rule_engine, and never reads
frame.rule_engine_output.facts. The one narrow widening this migration
introduces in its place is atlas.setup_interpretation.models
(SetupDirection) - the same "narrow, disclosed, not invented" precedent,
now pointing at the canonical interpretation layer instead of a raw Rule
Engine fact. See atlas.setup_interpretation's own ADR-0003 for why that
package exists and why Setup Engine/Rule Engine were never modified to
support it.

Every StrategyDecision this plugin can produce for a state genuinely
reachable through the real pipeline is unchanged from Sprint 3 - same
disposition, same direction, same reason_codes strings
("setup_absent"/"context_insufficient"/"context_conflict"/"accepted") -
proven by a dedicated real-data exact-equivalence study (Sprint 6's own
migration report), not merely asserted. StrategyDecision.reason_codes
intentionally does NOT adopt SetupInterpretation's own reason codes
(e.g. "trend_up") - the two vocabularies describe different layers (this
plugin's own acceptance rule vs. the interpretation's own evidence), the
same architectural split already established between
StrategyDecision.context_fingerprint and
SetupInterpretation.interpretation_fingerprint.

--- Context filter: exactly what the real Market Context contract supports ---

Rule 1 (insufficient/untrusted context -> reject): ContextQuality has
exactly three states (see atlas.market_context's own ADR) - TRUSTED
("trust the value"), DEGRADED ("trust it but flag a labeling
disagreement"), UNKNOWN ("don't trust it"). Only UNKNOWN is rejected here:
DEGRADED is explicitly documented as still-trustworthy for volatility (the
only Market Context signal this plugin's acceptance logic reads), so
treating it as untrusted would misuse Market Context's own documented
semantics rather than honor them. Unchanged by this migration - this gate
is orthogonal to Setup Interpretation entirely and is checked BEFORE the
interpretation lookup below, exactly as it was checked before the old
trend_5m read.

Rule 2 (interpretation direction determines acceptance): SetupDirection.
BULLISH/BEARISH accept as LONG/SHORT; AMBIGUOUS (a real, computed,
neutral/conflicting reading - e.g. this setup's own trend_5m coming back
"flat") rejects as context_conflict, exactly like the old "flat trend"
case did; UNAVAILABLE (the interpretation itself could not be produced -
e.g. trend_5m was insufficient_data) rejects as context_insufficient,
exactly like the old "trend not a FactResult" case did.

Rule 3 (NEUTRAL - defensive only): this setup's own interpretation rule
(SETUP_INTERPRETATION_V1) is RULE_FACT-sourced, and SetupInterpretation's
own model invariants require source=INTENTIONALLY_NEUTRAL for
direction=NEUTRAL - a combination _interpret_rule_fact() can never
produce. NEUTRAL is therefore structurally unreachable here through the
real pipeline (the same class of guarantee already established elsewhere
in this codebase, e.g. Setup Interpretation's own empty-qualifying-levels
case). It still gets a real, named branch - REJECTED/FLAT with a distinct,
honestly-labeled reason code - rather than a raise or a silent fallback,
because StrategyPlugin.evaluate()'s own contract promises it never raises
for an ordinary outcome, and a defensively-unreachable state is not the
same thing as a genuine internal contract violation (see
MissingSetupInterpretationError below for that distinct case).

--- Reason codes ---

Unchanged from Sprint 3, plus one new defensive-only addition:

    setup_absent                    the target setup was not present in
                                     frame.setup_engine_output.setups,
                                     could not be evaluated
                                     (InsufficientData), or was evaluated
                                     and did not detect (detected=False).
    context_insufficient            ContextQuality.UNKNOWN, or the
                                     matching SetupInterpretation's own
                                     direction is UNAVAILABLE.
    context_conflict                the matching SetupInterpretation's
                                     own direction is AMBIGUOUS.
    accepted                        the setup triggered, ContextQuality
                                     was TRUSTED or DEGRADED, and the
                                     matching SetupInterpretation gave a
                                     real BULLISH/BEARISH direction.
    unexpected_neutral_interpretation   Sprint 6's one new reason code -
                                     the defensive NEUTRAL branch above.
                                     Never expected in practice; included
                                     for total, honest evaluate() coverage.
"""
from atlas.market_context.models import ContextQuality
from atlas.replay_engine.models import ReplayFrame
from atlas.setup_engine.models import SetupResult
from atlas.setup_interpretation.models import SetupDirection
from atlas.strategy_engine.models import StrategyDecision, StrategyDirection, StrategyDisposition

STRATEGY_ID = "displacement_volume_context"
STRATEGY_VERSION = "1.0.0"
TARGET_SETUP_NAME = "displacement_with_volume_confirmation"

_INTERPRETED_DIRECTION = {
    SetupDirection.BULLISH: StrategyDirection.LONG,
    SetupDirection.BEARISH: StrategyDirection.SHORT,
}


class MissingSetupInterpretationError(Exception):
    """Raised when frame.setup_interpretations has no entry for
    TARGET_SETUP_NAME. ReplayFrame's own Sprint 5 contract guarantees a
    dense tuple - one SetupInterpretation per SetupOutcome in
    frame.setup_engine_output.setups - so a missing entry means Setup
    Engine's registry and Setup Interpretation's own SETUP_INTERPRETATION_V1
    rule set have gone out of sync: a real internal contract violation,
    never an ordinary market condition, and never silently papered over by
    falling back to Rule Engine facts. This mirrors the same "a real
    contract violation raises a typed, named exception" posture
    atlas.strategy_engine.service's own StrategyEvaluationError family
    already established for the service layer's own alignment checks -
    applied here one layer down, for a concrete plugin's own internal
    lookup."""


class DisplacementVolumeContext:
    """A deterministic reference strategy: displacement_with_volume_confirmation
    plus a minimal Market Context/Setup Interpretation acceptance filter.
    See this module's own docstring for the full decision-tree rationale."""

    @property
    def strategy_id(self) -> str:
        return STRATEGY_ID

    @property
    def strategy_version(self) -> str:
        return STRATEGY_VERSION

    def evaluate(self, frame: ReplayFrame) -> StrategyDecision:
        occurred_at = frame.market_state.envelope.occurred_at
        context_fingerprint = frame.market_context.context_fingerprint

        setup_outcome = next(
            (outcome for outcome in frame.setup_engine_output.setups if outcome.setup_name == TARGET_SETUP_NAME),
            None,
        )
        if not (isinstance(setup_outcome, SetupResult) and setup_outcome.detected):
            return StrategyDecision(
                occurred_at=occurred_at, strategy_id=STRATEGY_ID, strategy_version=STRATEGY_VERSION,
                disposition=StrategyDisposition.NO_SIGNAL, direction=StrategyDirection.FLAT,
                setup_ids=(), reason_codes=("setup_absent",), context_fingerprint=context_fingerprint,
            )

        if frame.market_context.quality == ContextQuality.UNKNOWN:
            return StrategyDecision(
                occurred_at=occurred_at, strategy_id=STRATEGY_ID, strategy_version=STRATEGY_VERSION,
                disposition=StrategyDisposition.REJECTED, direction=StrategyDirection.FLAT,
                setup_ids=(TARGET_SETUP_NAME,), reason_codes=("context_insufficient",),
                context_fingerprint=context_fingerprint,
            )

        interpretation = next(
            (entry for entry in frame.setup_interpretations if entry.setup_id == TARGET_SETUP_NAME), None,
        )
        if interpretation is None:
            raise MissingSetupInterpretationError(
                f"{TARGET_SETUP_NAME!r} has no entry in frame.setup_interpretations - ReplayFrame's own "
                "dense contract guarantees one, so this is an internal contract violation, not an "
                "ordinary market condition"
            )

        direction = _INTERPRETED_DIRECTION.get(interpretation.direction)
        if direction is not None:
            return StrategyDecision(
                occurred_at=occurred_at, strategy_id=STRATEGY_ID, strategy_version=STRATEGY_VERSION,
                disposition=StrategyDisposition.CANDIDATE, direction=direction,
                setup_ids=(TARGET_SETUP_NAME,), reason_codes=("accepted",),
                context_fingerprint=context_fingerprint,
            )

        if interpretation.direction == SetupDirection.AMBIGUOUS:
            return StrategyDecision(
                occurred_at=occurred_at, strategy_id=STRATEGY_ID, strategy_version=STRATEGY_VERSION,
                disposition=StrategyDisposition.REJECTED, direction=StrategyDirection.FLAT,
                setup_ids=(TARGET_SETUP_NAME,), reason_codes=("context_conflict",),
                context_fingerprint=context_fingerprint,
            )

        if interpretation.direction == SetupDirection.UNAVAILABLE:
            return StrategyDecision(
                occurred_at=occurred_at, strategy_id=STRATEGY_ID, strategy_version=STRATEGY_VERSION,
                disposition=StrategyDisposition.REJECTED, direction=StrategyDirection.FLAT,
                setup_ids=(TARGET_SETUP_NAME,), reason_codes=("context_insufficient",),
                context_fingerprint=context_fingerprint,
            )

        # SetupDirection.NEUTRAL - defensive only, structurally unreachable
        # through the real pipeline for this RULE_FACT-sourced setup (see
        # this module's own docstring). Kept as a real, named branch so
        # evaluate() stays total rather than raising for a state its own
        # Protocol promises never to raise for.
        return StrategyDecision(
            occurred_at=occurred_at, strategy_id=STRATEGY_ID, strategy_version=STRATEGY_VERSION,
            disposition=StrategyDisposition.REJECTED, direction=StrategyDirection.FLAT,
            setup_ids=(TARGET_SETUP_NAME,), reason_codes=("unexpected_neutral_interpretation",),
            context_fingerprint=context_fingerprint,
        )
