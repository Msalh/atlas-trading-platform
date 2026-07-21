"""
Setup Interpretation service - Sprint 2. interpret_setups() is the one
function this module defines: given one RuleEngineOutput/SetupEngineOutput
pair, applies SETUP_INTERPRETATION_V1's canonical rules (Sprint 1) and
returns exactly one SetupInterpretation per SetupOutcome, in the same
order.

Pure and synchronous: no I/O, no logging, no caching, no wall-clock read.
Recomputes nothing - every branch below reads an already-computed value
(SetupOutcome.detected, one specific Rule Engine FactResult.value, or one
specific fact's own evidence["qualifying_levels"][i]["side"]) and maps it
through SETUP_INTERPRETATION_V1's already-declared rule for that setup_id.
Which fact each rule reads (source_fact_ids) is never hardcoded a second
time here - it is read directly from the rule itself, the same "the
definition remains the one place this is configured" discipline
atlas.rule_engine.registry.FactRegistration.window_param already
established for window sizes.

Every reason_code below comes directly from SETUP_INTERPRETATION_V1's own
policy strings (bullish_reason/bearish_reason/neutral_policy/
ambiguous_policy/unavailable_policy) - nothing is hardcoded a second time
here. This module previously hardcoded a single "accepted" literal for
every successful directional call, bypassing the fingerprint guarantee
(a change to what that reason code should be would not have changed
interpretation_fingerprint); corrected so the definition, not this
module, owns every output-affecting string.

trend_5m's value contract is exactly "up"/"down"/"flat" (a closed,
three-way classification - see atlas.rule_engine.models.RuleEngineOutput's
own docstring). Any other value is a genuine upstream contract
violation, not a fourth market state - it is never silently coerced,
normalized, or reinterpreted as AMBIGUOUS; it raises
SetupInterpretationInvalidFactValueError instead. liquidity_sweep's own
"side" evidence has no analogous open-string risk (it comes from a fixed,
closed 2-value tuple in atlas.rule_engine.facts, never arbitrary input),
so no equivalent strict check applies there - the only two unmapped
side-sets possible are empty (structurally unreachable when detected=True)
and {"high","low"} (the real, already-modeled ambiguous case).
"""
from datetime import datetime

from atlas.rule_engine.models import FactResult, RuleEngineOutput
from atlas.setup_engine.models import SetupEngineOutput, SetupResult
from atlas.setup_interpretation.definitions import SETUP_INTERPRETATION_V1, SetupInterpretationRule
from atlas.setup_interpretation.fingerprint import compute_fingerprint
from atlas.setup_interpretation.models import DirectionSource, SetupDirection, SetupInterpretation

_INTERPRETATION_VERSION = SETUP_INTERPRETATION_V1.version
_INTERPRETATION_FINGERPRINT = compute_fingerprint(SETUP_INTERPRETATION_V1)


class SetupInterpretationError(Exception):
    """Base type for every Setup Interpretation service error. Catch this
    specifically to handle "the interpretation contract was violated"
    without also swallowing an unrelated bug - the same
    WindowIntegrityError/ReplayAlignmentError-style split this codebase
    already uses at every other pure-composition boundary."""


class SetupInterpretationAlignmentError(SetupInterpretationError):
    """Raised when rule_engine_output and setup_engine_output do not
    describe the same occurred_at - a caller error (the two must come
    from the same bar), not a data condition."""


class SetupInterpretationUnknownSetupError(SetupInterpretationError):
    """Raised when a SetupOutcome names a setup_id with no rule in
    SETUP_INTERPRETATION_V1 - a real architecture gap (a new setup was
    registered in Setup Engine without a corresponding interpretation
    rule being added here), reported rather than silently guessed at."""


class SetupInterpretationMissingFactError(SetupInterpretationError):
    """Raised when a rule's own source_fact_ids names a Rule Engine fact
    that is entirely absent from rule_engine_output.facts - not merely
    insufficient_data (an expected, already-modeled outcome), but
    genuinely missing, a structural mismatch reported rather than
    silently treated as ordinary insufficient data."""


class SetupInterpretationInvalidFactValueError(SetupInterpretationError):
    """Raised when a Rule Engine fact WAS successfully computed but its
    value falls outside the exact contract this interpretation rule
    relies on (trend_5m: "up"/"down"/"flat", nothing else) - a genuine
    upstream contract violation, never silently coerced, normalized, or
    reinterpreted as an ordinary market outcome. Distinct from
    SetupInterpretationMissingFactError (the fact was never computed at
    all) and from the ordinary insufficient_data path (an expected,
    already-modeled case, handled without raising)."""


def _rule_for(setup_id: str) -> SetupInterpretationRule:
    rule = next((r for r in SETUP_INTERPRETATION_V1.rules if r.setup_id == setup_id), None)
    if rule is None:
        raise SetupInterpretationUnknownSetupError(
            f"{setup_id!r} has no rule in {_INTERPRETATION_VERSION} - a new setup was likely registered "
            "in Setup Engine without a corresponding interpretation rule being added"
        )
    return rule


def _not_detected(occurred_at: datetime, setup_id: str, rule: SetupInterpretationRule) -> SetupInterpretation:
    return SetupInterpretation(
        occurred_at=occurred_at, setup_id=setup_id, detected=False,
        direction=SetupDirection.UNAVAILABLE, source=DirectionSource.INSUFFICIENT_DATA,
        source_fact_ids=(), reason_codes=(rule.params.unavailable_policy,),
        interpretation_version=_INTERPRETATION_VERSION, interpretation_fingerprint=_INTERPRETATION_FINGERPRINT,
    )


def _insufficient_source_fact(
    occurred_at: datetime, setup_id: str, rule: SetupInterpretationRule,
) -> SetupInterpretation:
    return SetupInterpretation(
        occurred_at=occurred_at, setup_id=setup_id, detected=True,
        direction=SetupDirection.UNAVAILABLE, source=DirectionSource.INSUFFICIENT_DATA,
        source_fact_ids=rule.params.source_fact_ids, reason_codes=(rule.params.unavailable_policy,),
        interpretation_version=_INTERPRETATION_VERSION, interpretation_fingerprint=_INTERPRETATION_FINGERPRINT,
    )


def _require_fact_result(setup_id: str, rule: SetupInterpretationRule, rule_engine_output: RuleEngineOutput):
    """Returns the FactResult for rule's own (single) source fact, or None
    if it was computed but came back insufficient_data. Raises
    SetupInterpretationMissingFactError if the fact key is absent from
    rule_engine_output.facts entirely."""
    fact_name = rule.params.source_fact_ids[0]
    if fact_name not in rule_engine_output.facts:
        raise SetupInterpretationMissingFactError(
            f"{setup_id!r} interpretation rule requires Rule Engine fact {fact_name!r}, "
            "which is absent from rule_engine_output.facts entirely"
        )
    outcome = rule_engine_output.facts[fact_name]
    return outcome if isinstance(outcome, FactResult) else None


def _directional(
    occurred_at: datetime, setup_id: str, rule: SetupInterpretationRule,
    direction: SetupDirection, source: DirectionSource, reason_code: str,
) -> SetupInterpretation:
    return SetupInterpretation(
        occurred_at=occurred_at, setup_id=setup_id, detected=True,
        direction=direction, source=source,
        source_fact_ids=rule.params.source_fact_ids, reason_codes=(reason_code,),
        interpretation_version=_INTERPRETATION_VERSION, interpretation_fingerprint=_INTERPRETATION_FINGERPRINT,
    )


def _ambiguous(
    occurred_at: datetime, setup_id: str, rule: SetupInterpretationRule, source: DirectionSource,
) -> SetupInterpretation:
    return SetupInterpretation(
        occurred_at=occurred_at, setup_id=setup_id, detected=True,
        direction=SetupDirection.AMBIGUOUS, source=source,
        source_fact_ids=rule.params.source_fact_ids, reason_codes=(rule.params.ambiguous_policy,),
        interpretation_version=_INTERPRETATION_VERSION, interpretation_fingerprint=_INTERPRETATION_FINGERPRINT,
    )


def _interpret_rule_fact(
    occurred_at: datetime, setup_id: str, rule: SetupInterpretationRule, rule_engine_output: RuleEngineOutput,
) -> SetupInterpretation:
    fact_result = _require_fact_result(setup_id, rule, rule_engine_output)
    if fact_result is None:
        return _insufficient_source_fact(occurred_at, setup_id, rule)

    value = fact_result.value
    if value == "up":
        return _directional(
            occurred_at, setup_id, rule, SetupDirection.BULLISH, DirectionSource.RULE_FACT,
            rule.params.bullish_reason,
        )
    if value == "down":
        return _directional(
            occurred_at, setup_id, rule, SetupDirection.BEARISH, DirectionSource.RULE_FACT,
            rule.params.bearish_reason,
        )
    if value == "flat":
        return _ambiguous(occurred_at, setup_id, rule, DirectionSource.RULE_FACT)

    fact_name = rule.params.source_fact_ids[0]
    raise SetupInterpretationInvalidFactValueError(
        f"{setup_id!r} interpretation rule requires Rule Engine fact {fact_name!r} to be "
        f"'up', 'down', or 'flat', got {value!r}"
    )


def _interpret_setup_evidence(
    occurred_at: datetime, setup_id: str, rule: SetupInterpretationRule, rule_engine_output: RuleEngineOutput,
) -> SetupInterpretation:
    fact_result = _require_fact_result(setup_id, rule, rule_engine_output)
    if fact_result is None:
        return _insufficient_source_fact(occurred_at, setup_id, rule)

    qualifying_levels = fact_result.evidence.get("qualifying_levels", [])
    sides = frozenset(level["side"] for level in qualifying_levels)
    if sides == frozenset({"low"}):
        return _directional(
            occurred_at, setup_id, rule, SetupDirection.BULLISH, DirectionSource.SETUP_EVIDENCE,
            rule.params.bullish_reason,
        )
    if sides == frozenset({"high"}):
        return _directional(
            occurred_at, setup_id, rule, SetupDirection.BEARISH, DirectionSource.SETUP_EVIDENCE,
            rule.params.bearish_reason,
        )
    return _ambiguous(occurred_at, setup_id, rule, DirectionSource.SETUP_EVIDENCE)


def _interpret_intentionally_neutral(
    occurred_at: datetime, setup_id: str, rule: SetupInterpretationRule,
) -> SetupInterpretation:
    return SetupInterpretation(
        occurred_at=occurred_at, setup_id=setup_id, detected=True,
        direction=SetupDirection.NEUTRAL, source=DirectionSource.INTENTIONALLY_NEUTRAL,
        source_fact_ids=rule.params.source_fact_ids, reason_codes=(rule.params.neutral_policy,),
        interpretation_version=_INTERPRETATION_VERSION, interpretation_fingerprint=_INTERPRETATION_FINGERPRINT,
    )


def _interpret_one(occurred_at: datetime, outcome, rule_engine_output: RuleEngineOutput) -> SetupInterpretation:
    setup_id = outcome.setup_name
    rule = _rule_for(setup_id)

    if not (isinstance(outcome, SetupResult) and outcome.detected):
        return _not_detected(occurred_at, setup_id, rule)

    if rule.params.expected_source == DirectionSource.RULE_FACT:
        return _interpret_rule_fact(occurred_at, setup_id, rule, rule_engine_output)
    if rule.params.expected_source == DirectionSource.SETUP_EVIDENCE:
        return _interpret_setup_evidence(occurred_at, setup_id, rule, rule_engine_output)
    return _interpret_intentionally_neutral(occurred_at, setup_id, rule)


def interpret_setups(
    *,
    rule_engine_output: RuleEngineOutput,
    setup_engine_output: SetupEngineOutput,
) -> tuple[SetupInterpretation, ...]:
    """Pure. Returns exactly one SetupInterpretation per SetupOutcome in
    setup_engine_output.setups, in the same order - never filtered, never
    reordered, never a shorter list, the same "one output per input"
    discipline every other windowed/sequence composer in this codebase
    already provides.

    Raises SetupInterpretationAlignmentError if rule_engine_output and
    setup_engine_output do not describe the same occurred_at (they must
    come from the same bar); SetupInterpretationUnknownSetupError if a
    SetupOutcome names a setup with no interpretation rule;
    SetupInterpretationMissingFactError if a rule's own source fact is
    entirely absent from rule_engine_output.facts;
    SetupInterpretationInvalidFactValueError if a source fact WAS computed
    but its value falls outside the exact contract this function relies
    on (trend_5m: "up"/"down"/"flat" only). None of these are caught or
    wrapped - a real mismatch is reported, never silently papered over."""
    if rule_engine_output.occurred_at != setup_engine_output.occurred_at:
        raise SetupInterpretationAlignmentError(
            f"rule_engine_output.occurred_at={rule_engine_output.occurred_at!r} does not match "
            f"setup_engine_output.occurred_at={setup_engine_output.occurred_at!r}"
        )
    occurred_at = datetime.fromisoformat(rule_engine_output.occurred_at)

    return tuple(
        _interpret_one(occurred_at, outcome, rule_engine_output)
        for outcome in setup_engine_output.setups
    )
