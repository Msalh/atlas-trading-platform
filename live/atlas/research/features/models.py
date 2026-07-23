"""
Phase N4 Sprint 4. Feature Registry's own domain types - the outcome of one
computation, and the declarative Candidate feature spec schema.

FeatureComputed/FeatureInsufficientData mirror
atlas.rule_engine.models.FactResult/InsufficientData's SHAPE exactly (a
successfully-computed outcome vs. an explicit "could not be computed"
outcome, never collapsed into each other - the same discipline Rule
Engine's own FactOutcome established at the platform's very first
certified layer) - but are NEW, Feature-Registry-owned types, never an
import of atlas.rule_engine.models itself, per Design Principle VIII.4
(research objects are never structurally interchangeable with production
ones, even when their shapes rhyme).

CandidateFeatureSpec is the declarative, closed-vocabulary schema a
Candidate feature's one fixed evaluator (candidate.py) interprets. Every
field is a closed enum or a bounded int - there is no free-form expression
field anywhere on this type, mirroring
atlas.research.models.AcceptanceCriterion's own "objective,
mechanically-checkable, no free-form expression" discipline. This is data,
never code: constructing a CandidateFeatureSpec can never itself execute
anything, and CandidateOperation/CandidateSourceField being closed enums
means an invalid operation or field cannot even be represented, let alone
evaluated - `CandidateOperation("eval")` raises ValueError before
candidate.py's evaluator is ever reached.

compute_feature_semantic_fingerprint() is the ONE place a Feature's
semantic fingerprint is computed - registry.py (Registered-tier
registration) and candidate.py (Candidate -> Registered promotion) both
call it, rather than each independently re-deriving the same curated
projection. {name, version, definition} only - deliberately excludes
tier, and every other id/lifecycle/audit field (feature_id, status,
provenance, created_at, description, its own fingerprint field): tier
and status both describe review/trust state (blueprint SS2.2's Feature
lifecycle - PROMOTED is a status transition, Registered/Candidate is a
tier distinction of the same kind), never what is computed. A Candidate
and its later-Promoted Registered counterpart correctly share this
fingerprint when name/version/definition are unchanged - computation
identity and lifecycle identity are two different axes, never conflated.
`name` stays in deliberately: two different computations (e.g. a mean vs.
a max) could share identical `definition` params, so `name` is the only
field distinguishing which evaluator logic a fingerprint actually
identifies.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Union

from atlas.research.fingerprint import compute_fingerprint


class CandidateOperation(str, Enum):
    """The complete, closed vocabulary of Candidate feature computations.
    Extending this list is a deliberate, reviewed model change - never
    something a spec's own data can introduce."""

    ROLLING_MEAN = "rolling_mean"
    ROLLING_MAX = "rolling_max"
    ROLLING_MIN = "rolling_min"


class CandidateSourceField(str, Enum):
    """The complete, closed vocabulary of MarketState fields a Candidate
    feature may read - deliberately limited to the plain-float fields
    (never a Price field, which would need its own unwrapping step,
    out of scope for this sprint's minimal, real example)."""

    ATR = "atr"
    VOLUME = "volume"
    VWAP = "vwap"
    VOLUME_RATIO = "volume_ratio"
    DISTANCE_FROM_VWAP_POINTS = "distance_from_vwap_points"


@dataclass(frozen=True)
class CandidateFeatureSpec:
    """window must be >= 1 - enforced in __post_init__, the same
    fail-at-construction discipline every other bounded field in this
    project already follows (e.g. Hypothesis's own acceptance_criteria
    check)."""

    operation: CandidateOperation
    source_field: CandidateSourceField
    window: int

    def __post_init__(self) -> None:
        if self.window < 1:
            raise ValueError(f"window must be >= 1, got {self.window}")


@dataclass(frozen=True)
class FeatureComputed:
    """A feature that was successfully computed over a window."""

    feature_name: str
    feature_version: str
    value: float


@dataclass(frozen=True)
class FeatureInsufficientData:
    """A feature that could NOT be computed - distinct from a feature that
    was computed and happened to evaluate to zero. `reason` names exactly
    what was missing, the same diagnosable-not-silent discipline
    InsufficientData's shape already established one layer down."""

    feature_name: str
    feature_version: str
    reason: str


FeatureOutcome = Union[FeatureComputed, FeatureInsufficientData]


def compute_feature_semantic_fingerprint(
    name: str, version: str, definition: Mapping[str, Union[int, float, str, bool]]
) -> str:
    """The curated projection every Feature's fingerprint is computed
    from, regardless of tier or lifecycle stage - see this module's own
    docstring for exactly which fields participate and why."""
    return compute_fingerprint({"name": name, "version": version, "definition": dict(definition)})
