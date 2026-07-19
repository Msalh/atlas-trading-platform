"""
Sprint 23B. Setup Engine's fourth real setup, and the first under
SetupFamily.CONFLUENCE (added Sprint 23A specifically for this setup - see
that enum's own docstring for the classification precedence and
anti-dumping-ground rule this setup was reviewed against before being
approved for this family).

detected = vwap_relationship.value != "within_band" AND volume_spike.value
is True - a bar where price is extended beyond the configured ATR-normalized
band around VWAP (either side) on the same bar volume_spike fires. The two
facts are independent by construction: vwap_relationship reads
distance_from_vwap_points/atr; volume_spike reads volume_ratio alone - no
shared field, no derivation from one to the other.

Deliberately interpretation-neutral, per this Sprint's explicit design
review (Sprint 22A/23A): this setup does NOT claim continuation, reversal,
exhaustion, mean reversion, momentum direction, trade entry quality, or
probability. Whether an extension-plus-volume-spike co-occurrence means
climactic exhaustion or strong continuation is genuinely ambiguous - Setup
Engine reports the structural co-occurrence, nothing more. This is exactly
why CONFLUENCE exists as a family rather than MOMENTUM or MEAN_REVERSION
(both of which would assert a thesis this setup does not hold).

Reads only vwap_relationship.value and volume_spike.value - never their
`.evidence` - deliberately: this setup does not re-derive or re-evaluate
ATR, VWAP distance, or volume ratio itself. Rule Engine already computed the
classification; Setup Engine composes the two already-computed value
contracts, nothing more, the same discipline every other
`_with_volume_confirmation` setup already follows.

Evidence deliberately does not copy full Rule Engine evidence into detail
(unlike displacement_with_volume_confirmation's and
liquidity_sweep_with_volume_confirmation's flat-evidence passthrough, which
was possible only because those facts' own evidence was already exactly
the bounded, scalar shape SupportingFact.detail requires). Instead, detail
carries only fields derived directly from the two fact values:
`vwap_relationship_value`/`volume_spike_value` (explicit, named copies of
each SupportingFact's own `.value` - redundant with that attribute by
design, not an oversight, so the `detail` dict alone is self-describing
without a caller needing to also read `.value`), `is_vwap_extended` (the
boolean half of the detection rule), and `extension_side` - present only
when actually extended, carrying vwap_relationship.value verbatim
("extended_above" or "extended_below"; never invented, never a third
directional label). No directional interpretation is added beyond
reporting which side the fact itself already classified.

Family is CONFLUENCE, not MEAN_REVERSION or MOMENTUM - see this module's own
docstring above and SetupFamily's docstring in models.py for the full
classification review.

Severity is fixed at NORMAL for every detected=True result, matching every
other setup built so far.
"""
from atlas.setup_engine.evidence import require_computed_fact, supporting_fact_from_rule_engine_output
from atlas.setup_engine.models import (
    SetupDefinition,
    SetupEvaluationContext,
    SetupEvidence,
    SetupFamily,
    SetupOutcome,
    SetupResult,
    Severity,
)
from atlas.setup_engine.registration import SetupRegistration

DEFAULT_VWAP_EXTENSION_WITH_VOLUME_CONFIRMATION_DEFINITION = SetupDefinition(
    name="vwap_extension_with_volume_confirmation",
    version="1.0",
    family=SetupFamily.CONFLUENCE,
    params={},
)


def evaluate_vwap_extension_with_volume_confirmation(
    context: SetupEvaluationContext, definition: SetupDefinition,
) -> SetupOutcome:
    current = context.current
    vwap_relationship = current.facts["vwap_relationship"]
    insufficient = require_computed_fact(vwap_relationship, definition.name, definition.version)
    if insufficient is not None:
        return insufficient

    volume_spike = current.facts["volume_spike"]
    insufficient = require_computed_fact(volume_spike, definition.name, definition.version)
    if insufficient is not None:
        return insufficient

    is_vwap_extended = vwap_relationship.value != "within_band"
    detected = is_vwap_extended and volume_spike.value is True

    vwap_detail = {
        "vwap_relationship_value": vwap_relationship.value,
        "is_vwap_extended": is_vwap_extended,
    }
    if is_vwap_extended:
        vwap_detail["extension_side"] = vwap_relationship.value

    vwap_fact = supporting_fact_from_rule_engine_output(current, "vwap_relationship", detail=vwap_detail)
    volume_spike_fact = supporting_fact_from_rule_engine_output(
        current, "volume_spike", detail={"volume_spike_value": volume_spike.value},
    )

    return SetupResult(
        setup_name=definition.name,
        definition_version=definition.version,
        detected=detected,
        severity=Severity.NORMAL if detected else None,
        evidence=SetupEvidence(supporting_facts=(vwap_fact, volume_spike_fact)),
    )


VWAP_EXTENSION_WITH_VOLUME_CONFIRMATION_REGISTRATION = SetupRegistration(
    name="vwap_extension_with_volume_confirmation",
    evaluate=evaluate_vwap_extension_with_volume_confirmation,
    definition=DEFAULT_VWAP_EXTENSION_WITH_VOLUME_CONFIRMATION_DEFINITION,
    required_facts=("vwap_relationship", "volume_spike"),
)
