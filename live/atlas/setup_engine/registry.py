"""
Sprint 17B. Setup Engine's registry - a direct generalization of
atlas.rule_engine.registry's FactRegistration/REGISTRY/validate_registry/
required_history, one layer up. See that module's own docstring for the
underlying discipline (params stays the single source of truth for window
sizes; a registration derives required_history from params on demand, never
a second independently-set copy).

Deliberately diverges from Rule Engine's registry on exactly one rule:
REGISTRY MAY be empty (validate_registry does not require non-empty) - Rule
Engine's own version added that requirement in Sprint 14, after six real
facts already existed; Setup Engine's registry started genuinely empty at
its Sprint 17B foundation. It held one real setup as of Sprint 18
(atlas.setup_engine.setups.displacement_with_volume_confirmation), two as of
Sprint 20 (atlas.setup_engine.setups.liquidity_sweep_with_volume_confirmation
added), and three as of Sprint 21
(atlas.setup_engine.setups.sustained_displacement_streak added - the first
registration with history_param set, so required_history(REGISTRY) below is
now 2, not 1).

SetupRegistration and SetupEvaluator live in atlas.setup_engine.registration,
not here (Sprint 18) - this module originally defined SetupRegistration
itself and imported each real setup module at the bottom of the file, after
the class existed, to avoid a circular import (a setup module needs
SetupRegistration to build its own registration; this module needs that
registration to build REGISTRY). That worked but didn't scale - every future
setup would need the same workaround. Splitting SetupRegistration into a
neutral module with no dependency on either this module or any setups/*.py
module removes the cycle entirely: this module can import the real setup
module normally, at the top, like anything else.
"""
from atlas.rule_engine.registry import REGISTRY as RULE_ENGINE_REGISTRY
from atlas.setup_engine.registration import SetupRegistration
from atlas.setup_engine.setups.displacement_with_volume_confirmation import (
    DISPLACEMENT_WITH_VOLUME_CONFIRMATION_REGISTRATION,
)
from atlas.setup_engine.setups.liquidity_sweep_with_volume_confirmation import (
    LIQUIDITY_SWEEP_WITH_VOLUME_CONFIRMATION_REGISTRATION,
)
from atlas.setup_engine.setups.sustained_displacement_streak import (
    SUSTAINED_DISPLACEMENT_STREAK_REGISTRATION,
)


def validate_registry(registry: tuple[SetupRegistration, ...]) -> None:
    """Fail-fast validation, run once at module-import time below. Unlike
    Rule Engine's validate_registry, does NOT require a non-empty registry -
    see this module's own docstring for why. Checks, for every registration:
    definition.name/version non-blank; registration.name matches
    definition.name; for a windowed registration, history_param names a
    present, positive int in definition.params (explicit bool-rejection,
    same reasoning as Rule Engine's own check); and every name in
    required_facts is a real, registered Rule Engine fact name."""
    names = [r.name for r in registry]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ValueError(f"REGISTRY contains duplicate setup names: {duplicates}")

    rule_engine_fact_names = {r.name for r in RULE_ENGINE_REGISTRY}

    for r in registry:
        if not r.definition.name or not r.definition.name.strip():
            raise ValueError(f"{r.name}: definition.name must not be blank")
        if not r.definition.version or not r.definition.version.strip():
            raise ValueError(f"{r.name}: definition.version must not be blank")
        if r.name != r.definition.name:
            raise ValueError(
                f"registration name {r.name!r} does not match definition.name {r.definition.name!r}"
            )

        if r.history_param is not None:
            if r.history_param not in r.definition.params:
                raise ValueError(
                    f"{r.name}: history_param {r.history_param!r} is not present in definition.params"
                )
            value = r.definition.params[r.history_param]
            if type(value) is not int:
                raise ValueError(
                    f"{r.name}: params[{r.history_param!r}] must be an int, "
                    f"got {type(value).__name__} ({value!r})"
                )
            if value < 1:
                raise ValueError(f"{r.name}: params[{r.history_param!r}] must be >= 1, got {value}")

        unknown_facts = sorted(set(r.required_facts) - rule_engine_fact_names)
        if unknown_facts:
            raise ValueError(
                f"{r.name}: required_facts names facts not present in Rule Engine's REGISTRY: "
                f"{unknown_facts}"
            )


REGISTRY: tuple[SetupRegistration, ...] = (
    DISPLACEMENT_WITH_VOLUME_CONFIRMATION_REGISTRATION,
    LIQUIDITY_SWEEP_WITH_VOLUME_CONFIRMATION_REGISTRATION,
    SUSTAINED_DISPLACEMENT_STREAK_REGISTRATION,
)


def required_history(registry: tuple[SetupRegistration, ...] = REGISTRY) -> int:
    """The history depth needed to satisfy every active setup - the maximum
    required_history across the registry, defaulting to 1 for an empty
    registry (max() over an empty generator would otherwise raise; Rule
    Engine's own version never needed this default since its registry could
    never legitimately be empty at the point that function was written)."""
    return max((r.required_history for r in registry), default=1)


validate_registry(REGISTRY)
