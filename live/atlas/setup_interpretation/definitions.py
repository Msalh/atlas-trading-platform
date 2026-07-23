"""
Versioned Setup Interpretation definitions - Sprint 1. Config as versioned
code, not env vars, the same discipline atlas.market_context.definitions
and atlas.rule_engine.models.FactDefinition already established: the
canonical interpretation ruleset lives in version control, tied to an
explicit version string, never runtime-configurable in a way that could
silently differ between deploys and break replay determinism.

Naming follows atlas.market_context.definitions' own convention exactly:
the one constant embeds its own version in its identifier - SETUP_
INTERPRETATION_V1, never DEFAULT_* - so a future _V2 can sit beside it
with no ambiguity about which is which, and the constant's own Python
name is required to equal its .version string exactly (verified by test,
not by runtime assertion - the same "no validation framework invented
here" posture FactDefinition/SessionCalendarDefinition already take).

Setups are identified by their stable string name
("displacement_with_volume_confirmation", etc.) - never by importing
atlas.setup_engine.registry.SETUP_ENGINE_REGISTRY or any SetupRegistration
- Sprint 1's own dependency boundary forbids importing atlas.setup_engine
at all, and a plain, stable string identifier is exactly what
atlas.setup_engine.models.SetupResult.setup_name already is, so there is
no type mismatch this choice introduces later.

This module imports DirectionSource from this package's own models.py -
an intra-package import, not a cross-package one; expressing "which
DirectionSource a setup's rule expects" as anything other than the real
enum (e.g. a second, independently-drifting string literal) would be
exactly the kind of duplicated-representation risk this whole project has
repeatedly avoided (FactRegistration never storing a second copy of a
window size Rule Engine's own FactDefinition.params already owns, is the
closest precedent).

--- The four current setups, and why each rule is what it is ---

Every rule below reflects only what each setup's OWN already-computed
evidence (or, for the two MOMENTUM-family setups, one specific,
externally-referenced Rule Engine fact) can honestly support - no new
market semantics are invented here; see the approved Phase N3 architecture
review's own mapping-table analysis for the full reasoning behind each
row. Sprint 2, not this module, is what will actually APPLY these rules
against real RuleEngineOutput/SetupEngineOutput data - this module only
declares them.

displacement_with_volume_confirmation / sustained_displacement_streak
(both MOMENTUM family): displacement's own evidence
(range/ATR ratio, volume/baseline ratio) is magnitude-only - genuinely no
sign. Direction, when available at all, is INFERRED from trend_5m - a
fact that is NOT among either setup's own required_facts. A flat trend_5m
reading is the ambiguous case: a real, computed, neutral trend classification
that does not support asserting either direction.

liquidity_sweep_with_volume_confirmation (ICT family): liquidity_sweep's
own evidence already tags every qualifying reference level with which
"side" it breached (high-side vs. low-side) - a high-side sweep-and-reject
is bearish, low-side is bullish, directly from the setup's own required
facts, no external fact needed. If both a high-side and a low-side level
qualify in the same bar, that is the ambiguous case - a real, structurally
possible mixed signal, never silently resolved to one side.

vwap_extension_with_volume_confirmation (CONFLUENCE family): this setup's
own docstring explicitly, deliberately declines to assert "continuation,
reversal, exhaustion, mean reversion, momentum direction... or probability"
even though its own vwap_relationship evidence (extended_above/
extended_below) looks directional. Treating it as directional here would
invent a thesis this setup's own author rejected - it is intentionally
neutral whenever detected, by design, never a per-bar judgment call.
"""
from dataclasses import dataclass

from atlas.setup_interpretation.models import DirectionSource


@dataclass(frozen=True)
class SetupInterpretationRuleParams:
    """One setup's own canonical interpretation rule. interpretation_mode
    is a short, stable, human-readable label - included in the fingerprint
    alongside expected_source so a change to how a rule is DESCRIBED (not
    only a change to the strict enum Sprint 2 will branch on) is still
    detectable.

    bullish_reason/bearish_reason/neutral_policy/ambiguous_policy/
    unavailable_policy are short, deterministic strings naming exactly
    what triggers each of the five possible outcomes for this setup -
    "not_applicable" where a given outcome can never legitimately occur
    for this setup, per the mapping analysis above. All five are
    definition-owned and therefore fingerprinted: the successful
    directional reason codes (bullish_reason/bearish_reason) are NOT
    hardcoded a second time in service.py (Sprint 2's own correction) -
    they live here, alongside the other three outcome reasons, so a
    change to any of the five is caught by the same interpretation
    fingerprint guarantee, not exempted from it."""

    interpretation_mode: str
    expected_source: DirectionSource
    source_fact_ids: tuple[str, ...]
    bullish_reason: str
    bearish_reason: str
    neutral_policy: str
    ambiguous_policy: str
    unavailable_policy: str


@dataclass(frozen=True)
class SetupInterpretationRule:
    setup_id: str
    params: SetupInterpretationRuleParams


@dataclass(frozen=True)
class SetupInterpretationDefinition:
    version: str
    rules: tuple[SetupInterpretationRule, ...]


_NOT_DETECTED_POLICY = "not_detected_or_source_fact_insufficient_data"

SETUP_INTERPRETATION_V1 = SetupInterpretationDefinition(
    version="SETUP_INTERPRETATION_V1",
    rules=(
        SetupInterpretationRule(
            setup_id="displacement_with_volume_confirmation",
            params=SetupInterpretationRuleParams(
                interpretation_mode="inferred_from_external_rule_fact",
                expected_source=DirectionSource.RULE_FACT,
                source_fact_ids=("trend_5m",),
                bullish_reason="trend_up",
                bearish_reason="trend_down",
                neutral_policy="not_applicable",
                ambiguous_policy="trend_flat",
                unavailable_policy=_NOT_DETECTED_POLICY,
            ),
        ),
        SetupInterpretationRule(
            setup_id="liquidity_sweep_with_volume_confirmation",
            params=SetupInterpretationRuleParams(
                interpretation_mode="direct_from_setup_evidence",
                expected_source=DirectionSource.SETUP_EVIDENCE,
                source_fact_ids=("liquidity_sweep",),
                bullish_reason="low_side_liquidity_sweep",
                bearish_reason="high_side_liquidity_sweep",
                neutral_policy="not_applicable",
                ambiguous_policy="conflicting_sides_in_qualifying_levels",
                unavailable_policy=_NOT_DETECTED_POLICY,
            ),
        ),
        SetupInterpretationRule(
            setup_id="sustained_displacement_streak",
            params=SetupInterpretationRuleParams(
                interpretation_mode="inferred_from_external_rule_fact",
                expected_source=DirectionSource.RULE_FACT,
                source_fact_ids=("trend_5m",),
                bullish_reason="trend_up",
                bearish_reason="trend_down",
                neutral_policy="not_applicable",
                ambiguous_policy="trend_flat",
                unavailable_policy=_NOT_DETECTED_POLICY,
            ),
        ),
        SetupInterpretationRule(
            setup_id="vwap_extension_with_volume_confirmation",
            params=SetupInterpretationRuleParams(
                interpretation_mode="intentionally_neutral_by_design",
                expected_source=DirectionSource.INTENTIONALLY_NEUTRAL,
                source_fact_ids=(),
                bullish_reason="not_applicable",
                bearish_reason="not_applicable",
                neutral_policy="always_neutral_when_detected",
                ambiguous_policy="not_applicable",
                unavailable_policy=_NOT_DETECTED_POLICY,
            ),
        ),
    ),
)
