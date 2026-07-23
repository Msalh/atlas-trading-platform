"""
Phase N4 Sprint 8. ResearchStrategyFactory - the one, narrow closed mapping
from a Realization's own (template_kind, version) pair to the concrete
ResearchStrategyPlugin implementation that executes it.

Sprint 8 architectural contract (purity): build_plugin()'s dispatch
decision - which plugin *class* gets selected - depends only on
realization.template_kind and realization.version. It never branches on
configuration, environment variables, feature flags, wall-clock time, or
any other runtime or global state; calling it twice with the same
(template_kind, version) always selects the identical class. This does not
forbid the selected class from being *constructed* with the rest of the
Realization (parameters, realization_id) - purity constrains which class,
never what that class is given once chosen. This purity is a prerequisite
for execute_realization()'s own end-to-end determinism, not merely a style
preference.

_DISPATCH is a plain, literal dict of class references - no importlib, no
entry-point discovery, no runtime register_plugin() call anywhere in this
codebase. Adding a template or a template version means adding one class
in templates.py and one literal line here, reviewed like any other code
change. Because Realization.version is an open string (not a closed enum),
this table can only be exhaustive over RealizationTemplateKind's own closed
category axis - test_research_backtesting.py's completeness test checks
exactly that, plus an explicit-failure test for a known category paired
with an unsupported version.
"""
from atlas.research.backtesting.ports import ResearchStrategyPlugin
from atlas.research.backtesting.templates import ThresholdCrossPlugin
from atlas.research.models import Realization, RealizationTemplateKind

_DISPATCH: dict[tuple[RealizationTemplateKind, str], type] = {
    (RealizationTemplateKind.THRESHOLD_CROSS, "v1"): ThresholdCrossPlugin,
}


def build_plugin(realization: Realization) -> ResearchStrategyPlugin:
    """realization.template_kind must be set - callers (execute_realization())
    are responsible for rejecting non-executable RealizationKinds before
    reaching here; Realization.__post_init__ already guarantees
    template_kind is non-None whenever kind requires one."""
    key = (realization.template_kind, realization.version)
    try:
        plugin_cls = _DISPATCH[key]
    except KeyError:
        raise ValueError(
            f"no registered plugin for template_kind={realization.template_kind!r}, "
            f"version={realization.version!r}"
        ) from None
    return plugin_cls(realization)
