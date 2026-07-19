"""
Sprint 17B/23C. This module holds exactly the helpers a setup's evaluate()
function needs to safely consume ONE required Rule Engine fact - the two
halves of that one concern, nothing broader:
- the success path: supporting_fact_from_rule_engine_output (build evidence
  from a fact that was actually computed)
- the insufficient-data path: require_computed_fact (Sprint 23C - extracted
  from three byte-identical copies once a third real, present setup made
  the duplication non-speculative to remove; see that Sprint's own
  architecture review for why this crossed the project's "no speculative
  abstraction" threshold and the magic-string VWAP-value question did not)

Setup-specific detection logic, severity logic, and business rules do NOT
belong in this module - only these two narrow "consume one fact safely"
helpers do. A future helper that doesn't fit that description needs its own
justified home, not a default assumption that this file is where setup
logic lives.

`detail` on supporting_fact_from_rule_engine_output remains an explicit,
setup-supplied parameter - it is not auto-derived from FactResult.evidence
(dict[str, Any], deliberately wider than SupportingFact.detail's bounded
type) because only the setup author knows which of a fact's evidence is
setup-relevant and already a bounded primitive.
"""
from collections.abc import Mapping
from types import MappingProxyType
from typing import Optional, Union

from atlas.rule_engine.models import FactOutcome, FactResult, RuleEngineOutput
from atlas.rule_engine.models import InsufficientData as FactInsufficientData
from atlas.setup_engine.models import InsufficientData, SupportingFact

_EMPTY_DETAIL: Mapping[str, Union[int, float, str, bool]] = MappingProxyType({})


def supporting_fact_from_rule_engine_output(
    output: RuleEngineOutput,
    fact_name: str,
    detail: Mapping[str, Union[int, float, str, bool]] = _EMPTY_DETAIL,
) -> SupportingFact:
    """Raises ValueError if fact_name is absent from output.facts or names an
    outcome that was not actually computed (InsufficientData) - a setup
    should already know, from its own required_facts-driven logic, that a
    fact was computed before asking this helper to build evidence from it;
    calling it otherwise is a bug in that setup, not a data condition."""
    if fact_name not in output.facts:
        raise ValueError(f"{fact_name!r} is not present in this RuleEngineOutput's facts")
    outcome = output.facts[fact_name]
    if not isinstance(outcome, FactResult):
        raise ValueError(
            f"{fact_name!r} was not computed for this RuleEngineOutput (insufficient_data) - "
            "cannot build supporting evidence from it"
        )
    return SupportingFact(
        fact_name=fact_name,
        occurred_at=output.occurred_at,
        value=outcome.value,
        detail=detail,
    )


def require_computed_fact(
    outcome: FactOutcome,
    setup_name: str,
    definition_version: str,
) -> Optional[InsufficientData]:
    """Sprint 23C. Returns a Setup Engine InsufficientData if `outcome` is a
    Rule Engine InsufficientData (the fact could not be computed), else
    None. Extracted unchanged from three identical copies
    (displacement_with_volume_confirmation, liquidity_sweep_with_volume_confirmation,
    vwap_extension_with_volume_confirmation) once a third real setup made
    the duplication non-speculative to remove."""
    if isinstance(outcome, FactInsufficientData):
        return InsufficientData(
            setup_name=setup_name, definition_version=definition_version,
            reason=f"{outcome.fact_name} is insufficient_data: {outcome.reason}",
        )
    return None
