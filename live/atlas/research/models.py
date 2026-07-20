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
"""
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class TargetKind(str, Enum):
    """Which of ProfilingReport's two metric namespaces an
    AcceptanceCriterion's `target` name refers to - fact names and setup
    names never collide in practice, but making the lookup explicit rather
    than "try fact_metrics, then setup_metrics" avoids relying on that
    never-colliding property implicitly."""

    FACT = "fact"
    SETUP = "setup"


class CriterionKind(str, Enum):
    """Closed, deliberately - the same discipline every other closed enum in
    this project already follows (SetupFamily, BarStatus, IngestOutcome).
    Exactly the two kinds Sprint 28's profiler-only scope can actually
    check; a hypothesis needing anything else (forward-return criteria, a
    correlation criterion) cannot be expressed yet, honestly, rather than
    approximated with the wrong kind."""

    MIN_FIRING_RATE = "min_firing_rate"
    MIN_COMPUTABLE_COUNT = "min_computable_count"


class HypothesisStatus(str, Enum):
    """Sprint 28 scope: no promotion pipeline exists yet, so REGISTERED and
    the outcome states below are set directly from one Experiment's result,
    not from a multi-stage state machine. Extending this into a full
    promotion lifecycle is future work, not built speculatively now."""

    REGISTERED = "registered"
    VALIDATED = "validated"
    REJECTED = "rejected"
    INCONCLUSIVE = "inconclusive"


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
    present benefit."""

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
    absent."""

    experiment_id: str
    hypothesis_id: str
    executed_at: str
    code_version: Optional[str]
    dataset_manifest: DatasetManifest
    criteria_results: tuple[CriterionResult, ...]
    passed: bool
    profiling_report_path: Optional[str]


@dataclass(frozen=True)
class ResearchReport:
    """The final artifact of one end-to-end research cycle - schema_version
    starts at "1.0", the same convention every other versioned output
    envelope in this project uses (RuleEngineOutput, SetupEngineOutput,
    ProfilingReport)."""

    schema_version: str
    hypothesis: Hypothesis
    experiment: Experiment
    conclusion: str
