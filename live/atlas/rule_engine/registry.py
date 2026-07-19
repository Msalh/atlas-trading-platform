"""
Sprint 14: a static, ordered registry of every active fact, replacing
Sprint 11-13's hardcoded dict literal in atlas.rule_engine.service and the
manually-maintained HISTORY_LIMIT constant it required. REGISTRY is
internal, in-package, static code - not a dynamic/pluggable registration API
(loading facts from outside this package, a decorator-based @register_fact,
etc. remain explicitly out of scope; see this Sprint's own review for why).

FactDefinition.params remains the single source of truth for configured
window sizes - FactRegistration never stores a second, independently-set
copy of a window value. A registration instead declares WHICH param (if
any) supplies its window requirement (`window_param`), and derives
`required_window` from that param on demand via a property, not a
separately-typed field that could drift out of sync with the definition.

validate_registry() runs once, at the bottom of this module (import time) -
REGISTRY is static internal code, so a validation failure here represents a
programming error, not a runtime/data condition, the same "refuse to start
unsafely" posture atlas.config.Settings.validate_for_startup() already
established for misconfigured environment variables. Fail fast and loud,
never silently proceed with a guessed or default value.
"""
from dataclasses import dataclass
from typing import Callable, Optional

from atlas.market_engine.models import MarketState
from atlas.rule_engine.definitions import (
    DEFAULT_DISPLACEMENT_DEFINITION,
    DEFAULT_LIQUIDITY_SWEEP_DEFINITION,
    DEFAULT_RECLAIM_DEFINITION,
    DEFAULT_REJECTION_DEFINITION,
    DEFAULT_TREND_5M_DEFINITION,
    DEFAULT_VOLUME_SPIKE_DEFINITION,
    DEFAULT_VWAP_RELATIONSHIP_DEFINITION,
)
from atlas.rule_engine.facts import (
    evaluate_displacement,
    evaluate_liquidity_sweep,
    evaluate_reclaim,
    evaluate_rejection,
    evaluate_trend_5m,
    evaluate_volume_spike,
    evaluate_vwap_relationship,
)
from atlas.rule_engine.models import FactDefinition, FactOutcome, InsufficientData

WindowedEvaluator = Callable[[list[MarketState], FactDefinition], FactOutcome]
SingleBarEvaluator = Callable[[MarketState, FactDefinition], FactOutcome]


def single_bar_adapter(evaluate: SingleBarEvaluator) -> WindowedEvaluator:
    """Adapts a single-bar evaluator (facts.py's original signature - takes
    one MarketState, not a window) into the registry's uniform,
    window-taking signature, using only the current (last) bar. Handles an
    empty window explicitly: InsufficientData is the correct outcome (there
    is nothing to evaluate), never an IndexError leaking out of `window[-1]`.
    `fact_name` for that InsufficientData is read from `definition.name`,
    not passed separately - validate_registry() below guarantees
    registration.name == registration.definition.name, so this is always
    the correct fact name, not a second value that could drift from it."""
    def adapted(window: list[MarketState], definition: FactDefinition) -> FactOutcome:
        if not window:
            return InsufficientData(
                fact_name=definition.name,
                definition_version=definition.version,
                reason="window is empty - no current bar to evaluate",
            )
        return evaluate(window[-1], definition)
    return adapted


@dataclass(frozen=True)
class FactRegistration:
    """One entry in REGISTRY. `evaluate` is always the uniform
    (list[MarketState], FactDefinition) -> FactOutcome signature - windowed
    facts (trend_5m, liquidity_sweep, reclaim) are registered directly
    (their facts.py functions already have this shape); single-bar facts
    (volume_spike, displacement, rejection) are wrapped via
    single_bar_adapter() at registration time, below - facts.py itself is
    never modified.

    `window_param` names which key in `definition.params` supplies this
    fact's required window size - None for single-bar facts. Deliberately
    NOT a separately stored integer: required_window (below) always reads
    live from `definition.params`, so FactDefinition remains the one place
    a window size is actually configured."""

    name: str
    evaluate: WindowedEvaluator
    definition: FactDefinition
    window_param: Optional[str] = None

    @property
    def required_window(self) -> int:
        """1 for single-bar facts. For windowed facts, derived directly from
        definition.params[window_param] - never a second, independently-set
        copy of that value. Assumes validate_registry() has already run
        (module-import time, below) and confirmed window_param names a
        present, positive int; this property does not re-validate on every
        access - it is a read, not a gate."""
        if self.window_param is None:
            return 1
        return self.definition.params[self.window_param]


REGISTRY: tuple[FactRegistration, ...] = (
    FactRegistration("volume_spike", single_bar_adapter(evaluate_volume_spike), DEFAULT_VOLUME_SPIKE_DEFINITION),
    FactRegistration("displacement", single_bar_adapter(evaluate_displacement), DEFAULT_DISPLACEMENT_DEFINITION),
    FactRegistration("rejection", single_bar_adapter(evaluate_rejection), DEFAULT_REJECTION_DEFINITION),
    FactRegistration("trend_5m", evaluate_trend_5m, DEFAULT_TREND_5M_DEFINITION, window_param="window"),
    FactRegistration("liquidity_sweep", evaluate_liquidity_sweep, DEFAULT_LIQUIDITY_SWEEP_DEFINITION, window_param="window"),
    FactRegistration("reclaim", evaluate_reclaim, DEFAULT_RECLAIM_DEFINITION, window_param="window"),
    # Sprint 22B - appended, not inserted among the single-bar facts above,
    # so REGISTRY's own history stays a clean, additive diff (the same
    # convention every past addition to any registry in this project has
    # followed). Single-bar despite its position after the windowed facts -
    # see its own docstring in facts.py.
    FactRegistration("vwap_relationship", single_bar_adapter(evaluate_vwap_relationship), DEFAULT_VWAP_RELATIONSHIP_DEFINITION),
)


def validate_registry(registry: tuple[FactRegistration, ...]) -> None:
    """Fail-fast validation - see this module's own docstring for why
    module-import time is the right place to run it. Checks, in order:
    non-empty; unique names; definition.name/version non-blank (an
    invariant FactDefinition itself does not enforce - checked defensively
    here rather than by modifying that model); registration.name matches
    registration.definition.name; and, for every windowed registration, that
    its window_param names a present, positive int in definition.params -
    explicitly rejecting bool (Python's bool is an int subclass, so a naive
    isinstance(value, int) check would wrongly accept True/False as a valid
    window size; `type(value) is int` does not have that problem)."""
    if not registry:
        raise ValueError("REGISTRY must not be empty")

    names = [r.name for r in registry]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ValueError(f"REGISTRY contains duplicate fact names: {duplicates}")

    for r in registry:
        if not r.definition.name or not r.definition.name.strip():
            raise ValueError(f"{r.name}: definition.name must not be blank")
        if not r.definition.version or not r.definition.version.strip():
            raise ValueError(f"{r.name}: definition.version must not be blank")
        if r.name != r.definition.name:
            raise ValueError(
                f"registration name {r.name!r} does not match definition.name {r.definition.name!r}"
            )

        if r.window_param is not None:
            if r.window_param not in r.definition.params:
                raise ValueError(
                    f"{r.name}: window_param {r.window_param!r} is not present in definition.params"
                )
            value = r.definition.params[r.window_param]
            if type(value) is not int:
                raise ValueError(
                    f"{r.name}: params[{r.window_param!r}] must be an int, "
                    f"got {type(value).__name__} ({value!r})"
                )
            if value < 1:
                raise ValueError(f"{r.name}: params[{r.window_param!r}] must be >= 1, got {value}")


def required_history(registry: tuple[FactRegistration, ...] = REGISTRY) -> int:
    """The history depth the live read path must fetch to satisfy every
    active fact - the maximum required_window across the registry.
    Supersedes Sprint 13's hardcoded HISTORY_LIMIT constant: this number is
    now a computed consequence of the registry, not a value a future Sprint
    has to remember to bump by hand when it adds a fact with a larger
    window."""
    return max(r.required_window for r in registry)


validate_registry(REGISTRY)
