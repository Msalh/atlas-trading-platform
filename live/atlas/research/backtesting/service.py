"""
Phase N4 Sprint 8. execute_realization() - the pure execution core this
package exists to provide. See this package's own __init__.py for the full
boundary (computes zero statistics; never validates, ranks, or promotes).
"""
from atlas.research.backtesting.factory import build_plugin
from atlas.research.backtesting.models import ResearchDecision
from atlas.research.models import Realization, RealizationKind
from atlas.research.replay_bridge import ReplayFrame

_EXECUTABLE_KINDS = (RealizationKind.TEMPLATED_STRATEGY, RealizationKind.STRATEGY_VARIANT)


def execute_realization(realization: Realization, frames: list[ReplayFrame]) -> tuple[ResearchDecision, ...]:
    """Pure: a deterministic function of (realization, frames) only - no
    I/O, no clock, no unseeded randomness. Constructs exactly one
    ResearchStrategyPlugin instance (via ResearchStrategyFactory) and calls
    its decide() once per frame, in order, returning one ResearchDecision
    per input frame.

    Rejects realization.kind values with no executable meaning this sprint
    (STATISTICAL_TEST/CONTEXT_FILTER/RISK_INPUT) explicitly, before ever
    touching the factory - a distinct, clearly-labeled failure mode from an
    unsupported (template_kind, version) pair, which the factory itself
    reports."""
    if realization.kind not in _EXECUTABLE_KINDS:
        raise ValueError(
            f"{realization.realization_id}: kind={realization.kind.value} has no executable meaning - "
            f"execute_realization() only supports {[k.value for k in _EXECUTABLE_KINDS]}"
        )

    plugin = build_plugin(realization)
    return tuple(plugin.decide(frame) for frame in frames)
