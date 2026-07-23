"""
Sprint 8.2. check_ledger_storage() - the write-side counterpart to
atlas.research_export.startup_check.check_snapshots(), same contract:
computed once at process start (atlas.main's lifespan calls this and
stores the result on app.state.ledger_readiness), never raises, never
blocks startup, never takes down LIVE endpoints over a research-storage
problem.

Five checks, in execution order (not necessarily the report's own display
order - see build_startup_report()):

1. configuration_valid - RESEARCH_LEDGER_DIR resolves to a non-blank path.
   Checked first and explicitly, rather than letting a blank path silently
   resolve against an ambiguous cwd-relative empty string.
2. ledger_directory - the directory exists (created if missing - a fresh
   Railway Volume starts empty).
3. volume_mounted - a real write-then-delete of a sentinel file. This is
   the closest proxy this process can check for "is this actually a
   persistent mount" - a single process cannot verify persistence across a
   restart by itself, only that the path is writable right now.
4. jsonl_stores_initialized - all nine atlas.research.stores classes
   construct without error (trivial - construction is just storing a
   path - but explicit, not assumed).
5. registries_available - a real .all() read on all nine stores succeeds,
   proving the read path works too, not only the write path.

Each check short-circuits the ones after it that would be meaningless
without it (no point checking writability of a directory that doesn't
exist) - but the run always returns a complete, well-formed LedgerReadiness
covering every check name, never a partial result a caller has to guess
the shape of.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

from atlas.research.stores import (
    EvidenceTracker,
    ExperimentTracker,
    FeatureRegistry,
    FindingTracker,
    HypothesisRegistry,
    LeaderboardSnapshotTracker,
    PromotionRecordTracker,
    RealizationRegistry,
    ValidationResultTracker,
)

LedgerCheckStatus = Literal["ready", "degraded"]

LEDGER_CHECK_NAMES = (
    "configuration_valid", "ledger_directory", "volume_mounted",
    "jsonl_stores_initialized", "registries_available",
)


@dataclass(frozen=True)
class LedgerStores:
    """One instance per atlas.research.stores class, all sharing the same
    RESEARCH_LEDGER_DIR directory - constructed once at startup
    (check_ledger_storage()) and attached to app.state, never re-constructed
    per request."""

    hypotheses: HypothesisRegistry
    experiments: ExperimentTracker
    features: FeatureRegistry
    findings: FindingTracker
    realizations: RealizationRegistry
    evidence: EvidenceTracker
    validation_results: ValidationResultTracker
    leaderboard_snapshots: LeaderboardSnapshotTracker
    promotions: PromotionRecordTracker

    def all_stores(self) -> tuple:
        return (
            self.hypotheses, self.experiments, self.features, self.findings, self.realizations,
            self.evidence, self.validation_results, self.leaderboard_snapshots, self.promotions,
        )


def _build_stores(directory: Path) -> LedgerStores:
    return LedgerStores(
        hypotheses=HypothesisRegistry(directory / "hypotheses.jsonl"),
        experiments=ExperimentTracker(directory / "experiments.jsonl"),
        features=FeatureRegistry(directory / "features.jsonl"),
        findings=FindingTracker(directory / "findings.jsonl"),
        realizations=RealizationRegistry(directory / "realizations.jsonl"),
        evidence=EvidenceTracker(directory / "evidence.jsonl"),
        validation_results=ValidationResultTracker(directory / "validation_results.jsonl"),
        leaderboard_snapshots=LeaderboardSnapshotTracker(directory / "leaderboard_snapshots.jsonl"),
        promotions=PromotionRecordTracker(directory / "promotions.jsonl"),
    )


@dataclass(frozen=True)
class LedgerCheckResult:
    name: str
    ok: bool
    detail: Optional[str]  # sanitized, operator-readable; never a raw path or traceback


@dataclass(frozen=True)
class LedgerReadiness:
    results: tuple[LedgerCheckResult, ...]

    @property
    def status(self) -> LedgerCheckStatus:
        return "ready" if all(r.ok for r in self.results) else "degraded"

    @property
    def reason(self) -> Optional[str]:
        """The name of the first failing check, in LEDGER_CHECK_NAMES
        order - None when status == 'ready'."""
        for r in self.results:
            if not r.ok:
                return r.name
        return None

    def result_for(self, name: str) -> LedgerCheckResult:
        for r in self.results:
            if r.name == name:
                return r
        raise KeyError(f"{name!r} is not one of the expected ledger checks")

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "reason": self.reason,
            "checks": {r.name: {"ok": r.ok, "detail": r.detail} for r in self.results},
        }


def internal_error_readiness() -> LedgerReadiness:
    """Fallback used by atlas.main's lifespan when check_ledger_storage()
    itself raises something this module did not anticipate - the same
    second, outer safety net check_snapshots()'s own
    internal_error_readiness() provides, never a relaxation of the "no
    check here may fail startup" contract."""
    return LedgerReadiness(tuple(
        LedgerCheckResult(name, False, "ledger readiness check failed unexpectedly at startup - see server logs")
        for name in LEDGER_CHECK_NAMES
    ))


def check_ledger_storage(directory: Path) -> tuple[LedgerReadiness, Optional[LedgerStores]]:
    """Pure aside from file I/O - safe to call at startup, and directly
    testable against a tmp_path fixture. Returns (readiness, stores) -
    stores is None only when a check failed badly enough that constructing
    them would be meaningless (blank config, unwritable directory);
    otherwise it's the real LedgerStores atlas.main should attach to
    app.state, so lifespan never constructs the nine stores twice."""
    results: list[LedgerCheckResult] = []

    directory_str = str(directory).strip()
    if not directory_str or directory_str == ".":
        results.append(LedgerCheckResult("configuration_valid", False, "RESEARCH_LEDGER_DIR resolves to a blank path"))
        results.extend(
            LedgerCheckResult(name, False, "skipped - configuration_valid failed")
            for name in LEDGER_CHECK_NAMES if name != "configuration_valid"
        )
        return LedgerReadiness(tuple(results)), None
    results.append(LedgerCheckResult("configuration_valid", True, None))

    try:
        directory.mkdir(parents=True, exist_ok=True)
        results.append(LedgerCheckResult("ledger_directory", True, None))
    except OSError:
        results.append(LedgerCheckResult("ledger_directory", False, "directory could not be created"))
        results.extend(
            LedgerCheckResult(name, False, "skipped - ledger_directory failed")
            for name in ("volume_mounted", "jsonl_stores_initialized", "registries_available")
        )
        return LedgerReadiness(tuple(results)), None

    sentinel = directory / ".startup_check"
    try:
        sentinel.write_text("ok", encoding="utf-8")
        sentinel.unlink()
        results.append(LedgerCheckResult("volume_mounted", True, None))
    except OSError:
        results.append(LedgerCheckResult("volume_mounted", False, "directory is not writable"))
        results.extend(
            LedgerCheckResult(name, False, "skipped - volume_mounted failed")
            for name in ("jsonl_stores_initialized", "registries_available")
        )
        return LedgerReadiness(tuple(results)), None

    stores = _build_stores(directory)
    results.append(LedgerCheckResult("jsonl_stores_initialized", True, None))

    try:
        for store in stores.all_stores():
            store.all()
        results.append(LedgerCheckResult("registries_available", True, None))
    except Exception:
        results.append(LedgerCheckResult("registries_available", False, "one or more registries could not be read"))

    return LedgerReadiness(tuple(results)), stores


def build_startup_report(readiness: LedgerReadiness, environment: str, elapsed_ms: float) -> str:
    """Renders the one-time, human-readable "Research Startup" block
    atlas.main's lifespan logs exactly once per process start (success or
    degraded - an operator needs this visibility most exactly when
    something failed, so this never goes silent on a degraded run).
    api_mounted/environment are static facts about the surrounding app
    startup, not filesystem checks - reported here, not by
    check_ledger_storage() itself, which only knows about the
    filesystem."""
    lines = ["Research Startup"]
    for name, label in (
        ("ledger_directory", "Ledger directory"),
        ("volume_mounted", "Volume mounted"),
        ("jsonl_stores_initialized", "JSONL stores initialized"),
        ("registries_available", "Registries available"),
        ("configuration_valid", "Configuration valid"),
    ):
        result = readiness.result_for(name)
        mark = "✓" if result.ok else "✗"
        suffix = f" ({result.detail})" if result.detail and not result.ok else ""
        lines.append(f"{mark} {label}{suffix}")
    lines.append("✓ API mounted")
    lines.append(f"✓ Environment: {environment}")
    outcome = "completed" if readiness.status == "ready" else "completed with degraded ledger storage"
    lines.append(f"Startup {outcome} in {elapsed_ms:.0f} ms")
    return "\n".join(lines)
