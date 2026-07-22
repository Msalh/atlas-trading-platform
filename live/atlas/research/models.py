"""
Sprint 28. The Research Engine's own domain model - a structural sibling of
atlas.profiling.models, one layer above it: Research Engine consumes
ProfilingReport (never MarketState/RuleEngineOutput/SetupEngineOutput
directly - it reuses atlas.profiling for that, never re-derives it) and
produces its own separately-owned record types. Same "never mutate or extend
what you consume" discipline every other layer in this project already
applies.

Sprint 28 scope, deliberately: Hypothesis acceptance criteria can only
reference what atlas.profiling.models.ProfilingReport already measures -
detection/firing-rate/sample-size questions. Forward returns, MAE/MFE, and
any statistical-significance criterion are NOT representable here yet,
because that capability does not exist yet (see
docs/market_engine/roadmap.md's Sprint 28 entry) - a Hypothesis registered
this Sprint is necessarily an observational claim about how often a fact or
setup fires, never an edge/profitability claim. CriterionKind's closed set
reflects this honestly; it is extended deliberately, the same "closed enum,
justified extension only" discipline SetupFamily already established, not
opened into a generic expression language.

--- Phase N4 Sprint 1 (Research Engine Core Entities) ---

Generalizes Hypothesis and Experiment in place, per
docs/phase-n4-research-engine-blueprint.md's own entity table, and adds the
remaining entities that table names: Feature, Finding, Realization,
Evidence, ValidationResult, LeaderboardEntry/LeaderboardSnapshot,
PromotionRecord. This sprint is data only - no behavior, no service
function, no storage. Every new field on the two pre-existing types
(Hypothesis, Experiment) is appended after the existing fields with an
explicit default, so every Sprint 28 call site
(atlas.research.service.run_experiment/build_research_report,
atlas.research.serialization, atlas.research.stores, and their own tests)
continues to construct both types exactly as before, completely unmodified.
CriterionKind/TargetKind/AcceptanceCriterion are deliberately untouched
this sprint - both reference atlas.profiling.models.ProfilingReport's own
metric namespaces, and extending them to reference Feature (Sprint 4, not
built yet) would be exactly the kind of speculative, unconsumable extension
this project's own design principles forbid (Research Engine Design
Principles, IX.1/VIII.5).

`Realization` represents the blueprint's five conceptual subtypes
(StatisticalTestRealization/TemplatedStrategyRealization/
StrategyVariantRealization/ContextFilterRealization/RiskInputRealization)
as one dataclass discriminated by a closed `RealizationKind` enum, mirroring
this exact module's own pre-existing AcceptanceCriterion/CriterionKind
shape, rather than five parallel classes with no kind-specific field or
behavior yet to justify the split (that split remains easy and additive
once Sprint 8's Backtesting work gives a real reason for one kind to need
fields another doesn't).

`provenance` (human/discovery_engine/ai_assistant - Research Engine Design
Principles VI.3) is carried by every entity that represents an authored
proposal or spec - Feature, Hypothesis, Realization, Experiment - and
deliberately NOT by Evidence or ValidationResult (both are always
system-computed, never authored, so a provenance field on them would be
constant and meaningless) or by Finding (already fully described by its own
`discovery_method`/`discovery_method_version` fields - a second field
naming the same fact would be exactly the kind of duplicated representation
this project has repeatedly avoided elsewhere, e.g.
FactRegistration never storing a second copy of a window size its own
FactDefinition.params already owns).

`fingerprint` (atlas.research.fingerprint.compute_fingerprint) is required,
non-optional, on every brand-new type here (Feature, Finding, Realization,
Evidence, ValidationResult, LeaderboardSnapshot, PromotionRecord) - none of
them has an existing caller to break, so there is no reason to default away
the same discipline atlas.setup_interpretation.models established from its
own Sprint 1 onward. It stays `Optional[str] = None` on the two
backward-compatible types (Hypothesis, Experiment) until the service layer
that populates it meaningfully (Experiment Builder, Sprint 5; Promotion,
Sprint 9) exists - constructing one now with a real fingerprint value is
possible (nothing prevents a caller from computing and passing one), just
not yet required.

A `PromotionRecord` is only ever constructed once a decision has actually
been made (APPROVED/DECLINED/DEFERRED) - there is no PENDING_REVIEW state
represented on this type at all, because "the permanent record of a human
decision" cannot exist before the decision does. PENDING_REVIEW is the
Hypothesis's own PROMOTION_CANDIDATE status (already part of its extended
lifecycle below), not a state of this type.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Optional, Union


class TargetKind(str, Enum):
    """Which namespace an AcceptanceCriterion's `target` name refers to -
    FACT/SETUP resolve against ProfilingReport's two metric namespaces;
    FEATURE (Phase N4 Sprint 5) resolves against a feature_id in
    atlas.research.features.registry.REGISTRY - fact/setup/feature names
    never collide in practice, but making the lookup explicit rather than
    "try each namespace in turn" avoids relying on that never-colliding
    property implicitly. FEATURE was deliberately deferred through Sprint
    1 ("extending TargetKind to reference Feature, not built yet, would
    be speculative") and added only now that atlas.research.features
    (Sprint 4) actually exists - additive only, FACT/SETUP unchanged."""

    FACT = "fact"
    SETUP = "setup"
    FEATURE = "feature"


class CriterionKind(str, Enum):
    """Closed, deliberately - the same discipline every other closed enum in
    this project already follows (SetupFamily, BarStatus, IngestOutcome).
    MIN_FIRING_RATE/MIN_COMPUTABLE_COUNT are exactly the two kinds Sprint
    28's profiler-only scope could check. MEAN_ABOVE_THRESHOLD (Phase N4
    Sprint 5) is the first kind targeting TargetKind.FEATURE - a
    hypothesis needing anything else (a below-threshold claim, a
    correlation criterion) cannot be expressed yet, honestly, rather than
    approximated with the wrong kind; additive only when a real need
    exists, per this enum's own established discipline."""

    MIN_FIRING_RATE = "min_firing_rate"
    MIN_COMPUTABLE_COUNT = "min_computable_count"
    MEAN_ABOVE_THRESHOLD = "mean_above_threshold"


class HypothesisStatus(str, Enum):
    """Sprint 28 defined the first four values only (REGISTERED and the
    three outcome states, set directly from one Experiment's result - no
    promotion pipeline existed yet). Phase N4 Sprint 1 extends this to the
    full lifecycle docs/phase-n4-research-engine-blueprint.md §2.2
    describes - additively: the four original values keep their exact
    original string, so nothing that already serialized a Sprint 28
    Hypothesis is affected. No service in this sprint transitions a
    Hypothesis between any of the new states - Formalization (Sprint 10),
    Validation (Sprint 6), Ranking (Sprint 7), and Promotion (Sprint 9) each
    own the transition that produces their own state, once built."""

    PROPOSED = "proposed"
    REGISTERED = "registered"
    UNDER_EXPERIMENT = "under_experiment"
    VALIDATED = "validated"
    REJECTED = "rejected"
    INCONCLUSIVE = "inconclusive"
    REALIZED = "realized"
    PROMOTION_CANDIDATE = "promotion_candidate"
    PROMOTED = "promoted"
    DECLINED = "declined"
    SUPERSEDED = "superseded"
    WITHDRAWN = "withdrawn"


class ProvenanceKind(str, Enum):
    """Research Engine Design Principles VI.3: immutable, fixed at creation,
    never inferred after the fact. AI_ASSISTANT is a real, valid value from
    Sprint 1 onward even though atlas.research.assistant does not exist
    until Sprint 14 - the field's own closed vocabulary is part of the
    entity model the blueprint specifies now, independent of when a real
    AI-authored record first appears."""

    HUMAN = "human"
    DISCOVERY_ENGINE = "discovery_engine"
    AI_ASSISTANT = "ai_assistant"


class FeatureTier(str, Enum):
    """Blueprint §1: Registered (code-defined, reviewed, permanent) vs.
    Candidate (declarative, auto-generatable, ephemeral until promoted).
    The registry/evaluator machinery that actually distinguishes how each
    tier is evaluated belongs to atlas.research.features (Sprint 4) - this
    sprint only defines the tier as data."""

    REGISTERED = "registered"
    CANDIDATE = "candidate"


class FeatureStatus(str, Enum):
    """Blueprint §2.2's Feature lifecycle: PROPOSED -> EVALUATED ->
    PROMOTED -> SUPERSEDED, or ARCHIVED at either of the first two steps."""

    PROPOSED = "proposed"
    EVALUATED = "evaluated"
    PROMOTED = "promoted"
    ARCHIVED = "archived"
    SUPERSEDED = "superseded"


class FindingStatus(str, Enum):
    """Blueprint §2.1: a Finding is Discovery Engine's raw, cheap,
    expected-to-be-mostly-noise output - DISCOVERED is its only entry
    state; every other state is terminal (DISMISSED/DUPLICATE/EXPIRED) or
    a handoff into the Hypothesis ledger (FORMALIZED)."""

    DISCOVERED = "discovered"
    DISMISSED = "dismissed"
    DUPLICATE = "duplicate"
    EXPIRED = "expired"
    FORMALIZED = "formalized"


class ClaimStrength(str, Enum):
    """Blueprint §6 (Discovery Engine, expanded): a causal claim requires
    materially more evidence than an associative one, and the two must
    never be silently conflated (Research Engine Design Principles, Section
    X anti-patterns table). Defaults to ASSOCIATIVE - every discovery
    method through Sprint 12 only ever produces associative claims;
    CAUSAL is a real, reachable value only once Sprint 13's causal
    discovery method exists, but the field itself is part of the entity
    model now, not retrofitted later."""

    ASSOCIATIVE = "associative"
    CAUSAL = "causal"


class RealizationKind(str, Enum):
    """The blueprint's five conceptual Realization subtypes, represented as
    one closed discriminator rather than five classes - see this module's
    own docstring for why."""

    STATISTICAL_TEST = "statistical_test"
    TEMPLATED_STRATEGY = "templated_strategy"
    STRATEGY_VARIANT = "strategy_variant"
    CONTEXT_FILTER = "context_filter"
    RISK_INPUT = "risk_input"


class RealizationStatus(str, Enum):
    """Blueprint §2.2's Realization lifecycle."""

    DRAFTED = "drafted"
    CONSTRUCTED = "constructed"
    EVALUATED = "evaluated"
    RETAINED = "retained"
    DISCARDED = "discarded"
    PROMOTED = "promoted"


class EvaluationMode(str, Enum):
    """Blueprint §1 (Experiment): single-run, walk-forward, or Monte Carlo.
    Only SINGLE is ever produced by anything built through Sprint 5;
    WALK_FORWARD/MONTE_CARLO become reachable once Sprint 6 (Validation)
    exists - the enum's full, closed vocabulary belongs to the entity model
    now regardless."""

    SINGLE = "single"
    WALK_FORWARD = "walk_forward"
    MONTE_CARLO = "monte_carlo"


class ExperimentStatus(str, Enum):
    """Blueprint §2.2's Experiment lifecycle. Sprint 28's own
    run_experiment() only ever produces a fully COMPLETED Experiment
    synchronously - CONSTRUCTED/RUNNING become meaningful once a
    longer-running walk-forward/Monte Carlo experiment (Sprint 6+) exists.
    Defaults to COMPLETED so every existing Sprint 28 call site's
    already-complete Experiment construction needs no change."""

    CONSTRUCTED = "constructed"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ValidationVerdict(str, Enum):
    """Blueprint §1 (ValidationResult): never a bare boolean - the verdict
    itself is one of exactly three values, always accompanied by the
    justification fields ValidationResult carries below (Research Engine
    Design Principles, IV.5)."""

    SUPPORTED = "supported"
    NOT_SUPPORTED = "not_supported"
    INCONCLUSIVE = "inconclusive"


class PromotionDecision(str, Enum):
    """Blueprint §1 (PromotionRecord)."""

    APPROVED = "approved"
    DECLINED = "declined"
    DEFERRED = "deferred"


@dataclass(frozen=True)
class AcceptanceCriterion:
    """One objective, mechanically-checkable condition against a
    ProfilingReport - never a human judgment call. `description` is the
    only free-text field; everything the checker actually evaluates is
    typed and closed."""

    description: str
    kind: CriterionKind
    target_kind: TargetKind
    target: str
    threshold: float


@dataclass(frozen=True)
class DatasetManifest:
    """Sprint 28's answer to "what data was this finding built from" -
    describes a resolved dataset, not a request for one (contrast
    atlas.profiling.models.ProfilingRunConfig, which is the request).
    Deliberately source-agnostic: built the same way whether the underlying
    MarketState list came from a repository query or a historical CSV
    import (Sprint 25B/26) - this type only describes what is IN the
    resolved dataset, never how it got there beyond the one free-text
    `source_description` field, mirroring how ProfilingReport.fact_metrics
    doesn't care whether its input came from live ingestion or replay."""

    symbol: str
    timeframe: str
    requested_start: str
    requested_end: str
    row_count: int
    first_occurred_at: Optional[str]
    last_occurred_at: Optional[str]
    source_description: str
    generated_at: str


@dataclass(frozen=True)
class Hypothesis:
    """Immutable once registered - the HypothesisRegistry (stores.py) never
    edits a record in place, only appends; see that module's own docstring
    for how "current status" is derived without mutating history, the same
    append-only discipline atlas.market_engine's event store already
    established. `acceptance_criteria` is deliberately a single list (no
    separate parallel rejection_criteria list) - rejection is "not every
    acceptance criterion passed," not a second thing to independently
    specify; Sprint 27's own review flagged uniform heavyweight process as a
    real risk, and a second criteria list here would be exactly that for no
    present benefit.

    Phase N4 Sprint 1 fields (all defaulted, all appended after the
    original Sprint 28 fields - see this module's own docstring):
    `provenance` names who/what authored this hypothesis;
    `origin_finding_id` links it back to the Finding it was formalized
    from, if any; `derived_from` links it to a prior Hypothesis it refines
    or was derived from (distinct from origin_finding_id - a hypothesis can
    be derived from another hypothesis without ever having started as a
    Finding); `feature_refs`/`context_description`/`outcome_metric` are the
    structured anchors a future similarity/duplicate check (Sprint 2's own
    minimal version, Sprint 11's full one) compares - `statement` remains
    free text for human readability, never parsed for structural
    similarity; `expected_relationship` is a short, honest, deliberately
    untyped description (e.g. "positive"/"elevated") - inventing a full
    typed claim-expression grammar now, with no real consumer yet, would be
    exactly the speculative generality this project's own principles
    forbid; `superseded_by` is the forward link Principle II.3 requires
    when a hypothesis is refined, never an edit to the superseded record
    itself; `fingerprint` stays None until Sprint 5's Experiment Builder (or
    a later sprint) computes one via atlas.research.fingerprint."""

    hypothesis_id: str
    registered_at: str
    author: str
    statement: str
    dataset_symbol: str
    dataset_timeframe: str
    dataset_start: str
    dataset_end: str
    acceptance_criteria: tuple[AcceptanceCriterion, ...]
    status: HypothesisStatus = HypothesisStatus.REGISTERED
    provenance: ProvenanceKind = ProvenanceKind.HUMAN
    origin_finding_id: Optional[str] = None
    derived_from: Optional[str] = None
    feature_refs: tuple[str, ...] = ()
    context_description: Optional[str] = None
    outcome_metric: Optional[str] = None
    expected_relationship: Optional[str] = None
    superseded_by: Optional[str] = None
    fingerprint: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.acceptance_criteria:
            raise ValueError(f"{self.hypothesis_id}: a hypothesis must state at least one acceptance criterion")


@dataclass(frozen=True)
class CriterionResult:
    """One AcceptanceCriterion checked against one ProfilingReport.
    `actual_value`/`reason` are None only when the criterion's target could
    not be found in the report at all (a structural problem - e.g. a typo'd
    fact name - never silently treated as a pass or a fail without
    explanation)."""

    criterion: AcceptanceCriterion
    actual_value: Optional[float]
    passed: bool
    reason: Optional[str]


@dataclass(frozen=True)
class Experiment:
    """Immutable, append-only record of one hypothesis actually being run.
    `code_version` is the git commit of the code that produced this result -
    easy to forget, load-bearing for reproducibility (an experiment's
    result is meaningless once the Rule/Setup Engine code it ran against
    has since changed) - None only when it genuinely could not be
    determined (not a git repository, or the check itself failed), never
    silently omitted without a reason being knowable from the field being
    absent.

    Phase N4 Sprint 1 fields (all defaulted, all appended after the
    original Sprint 28 fields): `realization_id` is set only for a
    decision-bearing Experiment (Sprint 8 onward) - None here means a
    decision-free, Stage-A statistical test, the normal case through
    Sprint 7; `dataset_manifests` is the plural, walk-forward-fold-capable
    form the blueprint specifies - empty by default, populated starting
    Sprint 6, deliberately kept alongside the original singular
    `dataset_manifest` rather than replacing it, since every Sprint 28 call
    site already constructs the singular field and nothing yet constructs
    the plural one; `evaluation_mode`/`seed` describe how (not yet built,
    Sprint 6); `status` defaults to COMPLETED, matching every Sprint 28
    Experiment's own synchronous, already-finished-when-constructed shape;
    `provenance` follows the same reasoning as Hypothesis's own new field,
    above.

    Two fingerprints, not one - added after the Sprint 1 fingerprint
    verification found that a single field cannot honestly answer both
    questions Experiment needs answered:

    `semantic_fingerprint` - "is this the same research question/
    configuration as another Experiment" - hashed from a curated projection
    of (hypothesis_id, realization_id, dataset_manifest(s),
    evaluation_mode) only. Deliberately excludes code_version and seed: two
    runs of the identical question against different code, or with
    different Monte Carlo draws, are still the same question. Used for
    grouping/multiple-testing accounting and for supersession comparisons.

    `execution_fingerprint` - "will re-running this reproduce byte-
    identical Evidence" - hashed from a projection of (semantic_fingerprint,
    code_version, seed, schema_version, and - once they exist - feature/
    evaluator/registry versions). This is the fingerprint
    docs/research-engine-design-principles.md Principle VII.1 actually
    means by "given the same fingerprint, re-running it must produce the
    same Evidence" - every axis that could change the computed result is
    folded in. Used for reproducibility checks, Evidence lineage (via
    Evidence.experiment_id), and caching.

    Both remain Optional[str] = None for the same backward-compatibility
    reason as Hypothesis.fingerprint: no Sprint 28 call site sets either
    field, and none is required to. See fingerprint.py's module docstring
    for the mechanical guard against hashing an Experiment (or any entity
    carrying its own fingerprint field) directly instead of a curated
    projection."""

    experiment_id: str
    hypothesis_id: str
    executed_at: str
    code_version: Optional[str]
    dataset_manifest: DatasetManifest
    criteria_results: tuple[CriterionResult, ...]
    passed: bool
    profiling_report_path: Optional[str]
    realization_id: Optional[str] = None
    dataset_manifests: tuple[DatasetManifest, ...] = ()
    evaluation_mode: EvaluationMode = EvaluationMode.SINGLE
    seed: Optional[int] = None
    status: ExperimentStatus = ExperimentStatus.COMPLETED
    provenance: ProvenanceKind = ProvenanceKind.HUMAN
    semantic_fingerprint: Optional[str] = None
    execution_fingerprint: Optional[str] = None


@dataclass(frozen=True)
class ResearchReport:
    """The final artifact of one end-to-end research cycle - schema_version
    starts at "1.0", the same convention every other versioned output
    envelope in this project uses (RuleEngineOutput, SetupEngineOutput,
    ProfilingReport). Untouched by Phase N4 Sprint 1."""

    schema_version: str
    hypothesis: Hypothesis
    experiment: Experiment
    conclusion: str


# =====================================================================
# Phase N4 Sprint 1 - new entities
# =====================================================================


@dataclass(frozen=True)
class Feature:
    """Blueprint §1. One named, versioned computation over MarketState/
    ReplayFrame-derived data, at either the Registered or Candidate tier -
    see FeatureTier's own docstring. `definition` mirrors
    atlas.rule_engine.models.FactDefinition.params's own shape and
    normalization exactly (a bounded Mapping, immutable in fact via
    MappingProxyType, not just by type hint) - this sprint defines the
    shape a feature's own tunable parameters/declarative spec take; the
    registry that registers Registered features and the fixed evaluator
    that interprets a Candidate feature's `definition` both belong to
    atlas.research.features (Sprint 4), not here."""

    feature_id: str
    name: str
    tier: FeatureTier
    version: str
    description: str
    definition: Mapping[str, Union[int, float, str, bool]]
    status: FeatureStatus
    provenance: ProvenanceKind
    created_at: str
    fingerprint: str
    superseded_by: Optional[str] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "definition", MappingProxyType(dict(self.definition)))
        if not self.name or not self.name.strip():
            raise ValueError("Feature.name must not be blank")


@dataclass(frozen=True)
class Finding:
    """Blueprint §1/§6. Discovery Engine's raw, cheap, expected-to-be-
    mostly-noise output - explicitly NOT a Hypothesis (see this module's
    own docstring and Research Engine Design Principles IV.1). `metrics` is
    a bounded Mapping, the same shape/normalization as Feature.definition
    above and atlas.rule_engine.models.FactResult.evidence one layer down -
    whatever numbers the discovery method itself computed (correlation,
    effect size, sample count, ...), never re-derived here.
    `claim_strength` defaults to ASSOCIATIVE - see ClaimStrength's own
    docstring. `formalized_into` is set if and only if status is
    FORMALIZED - the same unconstructable-invalid-state discipline
    atlas.setup_interpretation.models.SetupInterpretation already
    established for its own detected/direction/source triple."""

    finding_id: str
    discovered_at: str
    discovery_method: str
    discovery_method_version: str
    dataset_manifest: DatasetManifest
    feature_refs: tuple[str, ...]
    description: str
    metrics: Mapping[str, Union[int, float, str, bool]]
    status: FindingStatus
    fingerprint: str
    claim_strength: ClaimStrength = ClaimStrength.ASSOCIATIVE
    formalized_into: Optional[str] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "metrics", MappingProxyType(dict(self.metrics)))
        if self.status == FindingStatus.FORMALIZED and self.formalized_into is None:
            raise ValueError(f"{self.finding_id}: status=FORMALIZED requires formalized_into to be set")
        if self.status != FindingStatus.FORMALIZED and self.formalized_into is not None:
            raise ValueError(
                f"{self.finding_id}: formalized_into is set but status={self.status.value}, not FORMALIZED"
            )


@dataclass(frozen=True)
class Realization:
    """Blueprint §1. One executable/structural expression of a Hypothesis -
    see RealizationKind's own docstring for why this is one discriminated
    type rather than five. `parameters` mirrors Feature.definition's own
    bounded-Mapping shape exactly - a StrategyVariantRealization's tunable
    parameters, a StatisticalTestRealization's (typically empty) ones, or
    any other kind's, all fit the same closed value-type contract. The
    pure execution/statistics functions that actually consume a
    Realization belong to atlas.research.backtesting (Sprint 8) and
    atlas.research.statistics (Sprint 5); this sprint defines only the
    shape."""

    realization_id: str
    hypothesis_id: str
    kind: RealizationKind
    version: str
    parameters: Mapping[str, Union[int, float, str, bool]]
    status: RealizationStatus
    provenance: ProvenanceKind
    created_at: str
    fingerprint: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))


@dataclass(frozen=True)
class Evidence:
    """Blueprint §1 - merges the blueprint's own candidate names
    "Experiment Result" and "Evidence" into one type (see the blueprint's
    own explicit justification for that merge). The raw, computed output of
    one completed Experiment - metrics only, never a verdict (Research
    Engine Design Principles III.1: evidence is computed, not judged).
    `decision_sequence_path` mirrors Experiment.profiling_report_path's own
    established pattern exactly - a pointer to a larger, separately-stored
    artifact (a decision sequence, only present for a decision-bearing,
    Realization-backed Experiment), never embedded inline, for the same
    storage-efficiency reason Sprint 28 already chose a path over an inline
    ProfilingReport."""

    evidence_id: str
    experiment_id: str
    computed_at: str
    metrics: Mapping[str, Union[int, float, str, bool]]
    fingerprint: str
    decision_sequence_path: Optional[str] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "metrics", MappingProxyType(dict(self.metrics)))


@dataclass(frozen=True)
class ValidationResult:
    """Blueprint §1. The judgment layer, always separate from the Evidence
    it judges (Research Engine Design Principles III.1/IV.1). Never a bare
    boolean (IV.5): `criteria_results` and `justification` are always
    present, and `verdict` is one of exactly three values, never inferred
    from `criteria_results` alone by a caller. `multiple_testing_correction`
    is None only when this hypothesis was genuinely the only one tested
    against its dataset - a batch of more than one requires a real,
    recorded correction method (IV.4), enforced by service logic in Sprint
    6, not representable-but-unenforced here. `out_of_sample` records
    whether this verdict rests on out-of-sample/held-out evidence, the
    literal condition IV.3 requires before VALIDATED may ever be reached -
    that requirement is enforced by Sprint 6's own service logic; this
    field only records the fact for audit."""

    validation_id: str
    hypothesis_id: str
    evidence_ids: tuple[str, ...]
    verdict: ValidationVerdict
    criteria_results: tuple[CriterionResult, ...]
    justification: str
    validated_at: str
    out_of_sample: bool
    multiple_testing_correction: Optional[str]
    fingerprint: str

    def __post_init__(self) -> None:
        if not self.evidence_ids:
            raise ValueError(f"{self.validation_id}: a ValidationResult must reference at least one Evidence record")
        if not self.criteria_results:
            raise ValueError(f"{self.validation_id}: a ValidationResult must record at least one criterion result")
        if not self.justification or not self.justification.strip():
            raise ValueError(f"{self.validation_id}: justification must not be blank")


@dataclass(frozen=True)
class LeaderboardEntry:
    """One ranked position within a LeaderboardSnapshot. `realization_id`
    is None for a purely descriptive, decision-free hypothesis ranked
    without ever having a Realization - Ranking must be able to rank these
    (Research Engine Design Principles I.1/I.4; roadmap Sprint 7's own
    explicit ordering rationale), not only Realization-bearing entries."""

    hypothesis_id: str
    realization_id: Optional[str]
    rank: int
    score: float
    score_description: str


@dataclass(frozen=True)
class LeaderboardSnapshot:
    """Blueprint §1. A versioned, timestamped, permanent record of one
    ranking pass - past snapshots are never overwritten (Principle II.3),
    only ever superseded by a newer snapshot with its own id."""

    snapshot_id: str
    created_at: str
    entries: tuple[LeaderboardEntry, ...]
    fingerprint: str
    benchmark_description: Optional[str] = None

    def __post_init__(self) -> None:
        ranks = [entry.rank for entry in self.entries]
        if len(ranks) != len(set(ranks)):
            raise ValueError(f"{self.snapshot_id}: LeaderboardSnapshot entries must have unique ranks, got {ranks}")


@dataclass(frozen=True)
class PromotionRecord:
    """Blueprint §1. The permanent record of one human promotion decision -
    see this module's own docstring for why there is no PENDING_REVIEW
    state represented here. `rationale` is mandatory and non-blank
    (Principle V.2 - every promotion is explainable); `evidence_snapshot_ref`
    pins exactly what was reviewed (e.g. a ValidationResult id or a
    LeaderboardSnapshot id), so the decision remains reconstructable even
    after later evidence supersedes what was seen at review time.
    `resulting_production_change_ref` is None at creation and may remain
    None indefinitely for a DECLINED/DEFERRED record; how and when it is
    ever populated for an APPROVED one, once the separate production
    certification sprint it refers to actually completes, is Sprint 9's own
    concern - deliberately not decided by this data-only sprint."""

    promotion_id: str
    hypothesis_id: str
    realization_id: Optional[str]
    decision: PromotionDecision
    reviewer: str
    rationale: str
    evidence_snapshot_ref: str
    decided_at: str
    fingerprint: str
    resulting_production_change_ref: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.rationale or not self.rationale.strip():
            raise ValueError(f"{self.promotion_id}: PromotionRecord requires a non-blank rationale")
        if not self.reviewer or not self.reviewer.strip():
            raise ValueError(f"{self.promotion_id}: PromotionRecord requires a non-blank reviewer")
