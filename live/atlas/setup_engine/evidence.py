"""
Sprint 17B. A shared construction helper for SupportingFact, so a setup's
fact_name/occurred_at/value are always copied consistently from a
RuleEngineOutput rather than each setup hand-rolling the same extraction
slightly differently. `detail` remains an explicit, setup-supplied
parameter - it is not auto-derived from FactResult.evidence (dict[str, Any],
deliberately wider than SupportingFact.detail's bounded type) because only
the setup author knows which of a fact's evidence is setup-relevant and
already a bounded primitive.
"""
from collections.abc import Mapping
from types import MappingProxyType
from typing import Union

from atlas.rule_engine.models import FactResult, RuleEngineOutput
from atlas.setup_engine.models import SupportingFact

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
