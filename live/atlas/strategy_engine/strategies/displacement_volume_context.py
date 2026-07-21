"""
DisplacementVolumeContext - Phase N3, Sprint 3. The first concrete
StrategyPlugin: a deliberately minimal reference implementation proving
the full Strategy Engine path (evaluate_strategies -> StrategyPlugin ->
StrategyDecision) against real ReplayFrame inputs.

Recomputes nothing: every input this plugin reads is an already-computed,
already-typed field on the ReplayFrame it is given -
frame.setup_engine_output.setups (the "displacement_with_volume_confirmation"
SetupOutcome), frame.rule_engine_output.facts["trend_5m"] (Rule Engine's
own three-way up/down/flat classification), and frame.market_context.quality
(Market Context's own three-state ContextQuality). No OHLC is read
directly; no displacement/volume/trend value is recalculated.

--- Dependency boundary correction, disclosed ---

Sprint 1's dependency ceiling for atlas.strategy_engine (models.py/ports.py)
deliberately excluded atlas.rule_engine, reasoning that Strategy Engine
would only ever reach RuleEngineOutput through ReplayFrame's own
already-typed field, never needing to import atlas.rule_engine.models
directly. A concrete strategy that actually reads a specific fact's
outcome breaks that reasoning: frame.rule_engine_output.facts values are
typed FactOutcome = Union[FactResult, InsufficientData]
(atlas.rule_engine.models), and there is no way to safely branch on
"was this fact actually computed" without importing at least FactResult -
the exact same thing atlas.setup_engine.evidence.require_computed_fact
already does (`isinstance(outcome, FactResult)`) to safely consume one
Rule Engine fact from inside Setup Engine. This module imports exactly
FactResult, nothing else from atlas.rule_engine - the same narrow,
disclosed-not-invented widening precedent
atlas.market_context.regime's own window_integrity exception already
established one layer down. Sprint 3's own instructions explicitly
anticipated this ("derive LONG/SHORT only from existing typed Setup
Engine OR RULE ENGINE output").

--- Direction source: why trend_5m, and why Market Context has none ---

atlas.rule_engine.facts.evaluate_displacement's own evidence
({"range_atr_ratio", "threshold"}) and evaluate_volume_spike's own
evidence ({"volume_ratio", "threshold"}) are both magnitude-only - a bar's
range and volume relative to their own baselines, never a sign. The
displacement_with_volume_confirmation setup itself is `detected =
displacement.value AND volume_spike.value`, a pure boolean AND of two
magnitude facts - it carries no directional information on its own.
Market Context (SessionPhase, SessionProgress, DriftStatus,
VolatilityRegime, ContextQuality) carries none either - volatility REGIME
is about the magnitude of movement, not its sign, and session/drift
concern time-of-day and upstream agreement, not price direction. The only
existing, typed, directional signal anywhere in this pipeline is Rule
Engine's own trend_5m fact (a three-way "up"/"down"/"flat"
classification) - read directly off
frame.rule_engine_output.facts["trend_5m"], never recomputed.

--- Context filter: exactly what the real Market Context contract supports ---

Rule 1 (insufficient/untrusted context -> reject): ContextQuality has
exactly three states (see atlas.market_context's own ADR) - TRUSTED
("trust the value"), DEGRADED ("trust it but flag a labeling
disagreement"), UNKNOWN ("don't trust it"). Only UNKNOWN is rejected here:
DEGRADED is explicitly documented as still-trustworthy for volatility (the
only Market Context signal this plugin's acceptance logic reads), so
treating it as untrusted would misuse Market Context's own documented
semantics rather than honor them.

Rule 2 (regime/trend conflicts with direction -> reject): Market Context's
own models carry no directional semantics at all (see above) - there is
no second, independent "regime" signal to cross-check trend_5m's
direction against without inventing one, which this Sprint's instructions
explicitly forbid. The one faithful, non-invented reading of this rule is
trend_5m's own "flat" value: a real, computed, neutral trend that does
not support asserting either LONG or SHORT - a genuine conflict between
the trend classification and any directional claim this plugin might
otherwise make, using no signal beyond what already exists.

Rule 3 (accept neutral/unknown only if defensible): this implementation
never defaults to acceptance for an unclear signal - ContextQuality.UNKNOWN,
trend_5m's own InsufficientData, and trend_5m's "flat" value are all
rejected, never treated as "safe to trade" by default.

--- Reason codes ---

Exactly the four this Sprint's own instructions gave as examples -
nothing invented beyond them:

    setup_absent          the target setup was not present in
                           frame.setup_engine_output.setups, could not be
                           evaluated (InsufficientData), or was evaluated
                           and did not detect (detected=False). All three
                           collapse to one NO_SIGNAL/FLAT outcome - "not
                           present or did not trigger" is one condition,
                           per this Sprint's own wording.
    context_insufficient   ContextQuality.UNKNOWN, or trend_5m itself
                           could not be computed (InsufficientData) - not
                           enough information to accept a candidate.
    context_conflict       trend_5m computed a real "flat" classification -
                           conflicts with asserting any direction.
    accepted               the setup triggered, ContextQuality was TRUSTED
                           or DEGRADED, and trend_5m gave a real up/down
                           direction.
"""
from atlas.market_context.models import ContextQuality
from atlas.replay_engine.models import ReplayFrame
from atlas.rule_engine.models import FactResult
from atlas.setup_engine.models import SetupResult
from atlas.strategy_engine.models import StrategyDecision, StrategyDirection, StrategyDisposition

STRATEGY_ID = "displacement_volume_context"
STRATEGY_VERSION = "1.0.0"
TARGET_SETUP_NAME = "displacement_with_volume_confirmation"

_TREND_DIRECTION = {"up": StrategyDirection.LONG, "down": StrategyDirection.SHORT}


class DisplacementVolumeContext:
    """A deterministic reference strategy: displacement_with_volume_confirmation
    plus a minimal Market Context/trend acceptance filter. See this
    module's own docstring for the full decision-tree rationale."""

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

        trend = frame.rule_engine_output.facts.get("trend_5m")
        if not isinstance(trend, FactResult):
            return StrategyDecision(
                occurred_at=occurred_at, strategy_id=STRATEGY_ID, strategy_version=STRATEGY_VERSION,
                disposition=StrategyDisposition.REJECTED, direction=StrategyDirection.FLAT,
                setup_ids=(TARGET_SETUP_NAME,), reason_codes=("context_insufficient",),
                context_fingerprint=context_fingerprint,
            )

        direction = _TREND_DIRECTION.get(trend.value)
        if direction is None:
            return StrategyDecision(
                occurred_at=occurred_at, strategy_id=STRATEGY_ID, strategy_version=STRATEGY_VERSION,
                disposition=StrategyDisposition.REJECTED, direction=StrategyDirection.FLAT,
                setup_ids=(TARGET_SETUP_NAME,), reason_codes=("context_conflict",),
                context_fingerprint=context_fingerprint,
            )

        return StrategyDecision(
            occurred_at=occurred_at, strategy_id=STRATEGY_ID, strategy_version=STRATEGY_VERSION,
            disposition=StrategyDisposition.CANDIDATE, direction=direction,
            setup_ids=(TARGET_SETUP_NAME,), reason_codes=("accepted",),
            context_fingerprint=context_fingerprint,
        )
