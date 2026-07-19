"""
Sprint 18. SetupRegistration and the SetupEvaluator type alias, split out of
registry.py into their own neutral module.

registry.py originally defined SetupRegistration itself and imported each
real setup module at the bottom of the file (after the class existed) to
avoid a circular import: a setup module needs SetupRegistration to construct
its own registration instance, and registry.py needs that instance to build
REGISTRY. That bottom-import worked but does not scale - every new setup
module still needs SetupRegistration, and registry.py still needs to import
every setup module, so the same cycle would have to be worked around again
for each one.

This module depends only on atlas.setup_engine.models - never on
atlas.setup_engine.registry or on any atlas.setup_engine.setups.* module.
Both registry.py and every setups/*.py module import SetupRegistration from
here instead, so no import-order workaround is needed anywhere, now or as
more setups are added.
"""
from dataclasses import dataclass, field
from typing import Callable, Optional

from atlas.setup_engine.models import SetupDefinition, SetupEvaluationContext, SetupOutcome

SetupEvaluator = Callable[[SetupEvaluationContext, SetupDefinition], SetupOutcome]


@dataclass(frozen=True)
class SetupRegistration:
    """One entry in atlas.setup_engine.registry.REGISTRY. `history_param`
    names which key in definition.params supplies this setup's required
    history depth (None -> 1) - never a separately stored integer, the same
    reasoning atlas.rule_engine.registry.FactRegistration.window_param
    already established. `required_facts` names which Rule Engine fact names
    this setup's evaluate() reads - cross-validated by
    atlas.setup_engine.registry.validate_registry against Rule Engine's own
    REGISTRY, not accepted unchecked."""

    name: str
    evaluate: SetupEvaluator
    definition: SetupDefinition
    history_param: Optional[str] = None
    required_facts: tuple[str, ...] = field(default_factory=tuple)

    @property
    def required_history(self) -> int:
        if self.history_param is None:
            return 1
        return self.definition.params[self.history_param]
