"""
Phase N4 Sprint 2 (Ledger). Protocol boundaries for every Research Engine
store - one per entity, matching each concrete stores.py class's own method
signatures exactly. Python's structural typing already satisfies membership
without any concrete class declaring these Protocols as a base - none of
stores.py's classes are modified to do so.

Modeled on atlas.market_engine.ports.MarketStateRepository's own role: a
Protocol boundary so a future concrete implementation (the roadmap's own
named trigger - when a JSONL file's linear scan stops being adequate) can be
swapped in one call site at a time without any caller needing to change,
the same "depend on the Protocol, not the concrete class" discipline
atlas.repositories.base.TradeRepository already established one layer down.
Sync, not async, here - deliberately: every concrete implementation in this
package today is sync file I/O, unlike Market Engine's own already-async
Postgres-backed implementation. The Protocol matches what actually exists,
not what a future implementation might require.

@runtime_checkable on every Protocol below so a store's conformance can be
proven mechanically (isinstance(concrete_instance, ProtocolType) in the test
suite) rather than only claimed in a docstring - the same "enforce
mechanically, not by convention alone" posture already applied to this
package's dependency boundaries and its fingerprint self-reference guard.
"""
from typing import Optional, Protocol, runtime_checkable

from atlas.research.models import (
    Evidence,
    Experiment,
    Feature,
    Finding,
    Hypothesis,
    LeaderboardSnapshot,
    PromotionRecord,
    Realization,
    ValidationResult,
)


@runtime_checkable
class HypothesisStore(Protocol):
    def register(self, hypothesis: Hypothesis) -> None: ...
    def get(self, hypothesis_id: str) -> Optional[Hypothesis]: ...
    def all(self) -> list[Hypothesis]: ...


@runtime_checkable
class ExperimentStore(Protocol):
    def record(self, experiment: Experiment) -> None: ...
    def get(self, experiment_id: str) -> Optional[Experiment]: ...
    def all(self) -> list[Experiment]: ...
    def for_hypothesis(self, hypothesis_id: str) -> list[Experiment]: ...


@runtime_checkable
class FeatureStore(Protocol):
    def register(self, feature: Feature) -> None: ...
    def get(self, feature_id: str) -> Optional[Feature]: ...
    def all(self) -> list[Feature]: ...


@runtime_checkable
class FindingStore(Protocol):
    def record(self, finding: Finding) -> None: ...
    def get(self, finding_id: str) -> Optional[Finding]: ...
    def all(self) -> list[Finding]: ...


@runtime_checkable
class RealizationStore(Protocol):
    def register(self, realization: Realization) -> None: ...
    def get(self, realization_id: str) -> Optional[Realization]: ...
    def all(self) -> list[Realization]: ...


@runtime_checkable
class EvidenceStore(Protocol):
    def record(self, evidence: Evidence) -> None: ...
    def get(self, evidence_id: str) -> Optional[Evidence]: ...
    def all(self) -> list[Evidence]: ...


@runtime_checkable
class ValidationResultStore(Protocol):
    def record(self, result: ValidationResult) -> None: ...
    def get(self, validation_id: str) -> Optional[ValidationResult]: ...
    def all(self) -> list[ValidationResult]: ...


@runtime_checkable
class LeaderboardSnapshotStore(Protocol):
    def record(self, snapshot: LeaderboardSnapshot) -> None: ...
    def get(self, snapshot_id: str) -> Optional[LeaderboardSnapshot]: ...
    def all(self) -> list[LeaderboardSnapshot]: ...


@runtime_checkable
class PromotionRecordStore(Protocol):
    def record(self, promotion: PromotionRecord) -> None: ...
    def get(self, promotion_id: str) -> Optional[PromotionRecord]: ...
    def all(self) -> list[PromotionRecord]: ...
