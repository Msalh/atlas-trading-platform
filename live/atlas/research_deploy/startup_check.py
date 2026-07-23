"""
Sprint 8.2, corrected. check_ledger_storage() - the write-side counterpart
to atlas.research_export.startup_check.check_snapshots(), same contract:
computed once at process start (atlas.main's lifespan calls this and
stores the result on app.state.ledger_readiness), never raises, never
blocks startup, never takes down LIVE endpoints over a research-storage
problem.

--- Production-safety correction ---

check_ledger_storage() takes Optional[Path], not Path. `directory=None`
means "RESEARCH_LEDGER_DIR must be treated as unconfigured for this
environment" - the caller (atlas.main's lifespan, via
Settings.resolved_research_ledger_dir()) is the one place that decides
whether a missing/blank RESEARCH_LEDGER_DIR gets a development-only
convenience default or must surface as unconfigured. This module never
makes that environment-dependent call itself; it only reacts to whatever
Optional[Path] it's given. A None here short-circuits every filesystem
check with reason="research_ledger_not_configured" and returns
stores=None - there is no path to construct LedgerStores against, and
critically, NO mkdir/write of any kind happens, so a missing production
config can never silently create or use an implicit, possibly-ephemeral
directory. This is the fix for a real false-positive risk: a relative
default path can be writable on Railway's own ephemeral filesystem, which
would make startup readiness, the smoke test, and every Ledger write all
report success right up until the next redeploy silently erased
everything.

Five checks, in execution order (not necessarily the report's own display
order - see build_startup_report()):

1. configuration_valid - directory is not None, and (if callers still pass
   a literal blank Path directly - a distinct, defensive case from "None
   was passed") not a blank/"." path either.
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
without it - but the run always returns a complete, well-formed
LedgerReadiness covering every check name, never a partial result a caller
has to guess the shape of.
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

REASON_NOT_CONFIGURED = "research_ledger_not_configured"
REASON_BLANK_PATH = "blank_path"
REASON_DIRECTORY_NOT_CREATABLE = "directory_not_creatable"
REASON_NOT_WRITABLE = "not_writable"
REASON_REGISTRIES_UNREADABLE = "registries_unreadable"
REASON_SKIPPED = "skipped"
REASON_INTERNAL_ERROR = "internal_error"


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
    reason: Optional[str]  # stable, machine-readable code - None only when ok
    detail: Optional[str]  # sanitized, operator-readable; never a raw path or traceback


@dataclass(frozen=True)
class LedgerReadiness:
    results: tuple[LedgerCheckResult, ...]

    @property
    def status(self) -> LedgerCheckStatus:
        return "ready" if all(r.ok for r in self.results) else "degraded"

    @property
    def reason(self) -> Optional[str]:
        """The first failing check's own stable reason code, in
        LEDGER_CHECK_NAMES order - None when status == 'ready'. Mirrors
        atlas.research_export.startup_check.SnapshotsReadiness.reason's own
        precedent exactly: a stable code, never a check name, never free
        text."""
        for r in self.results:
            if not r.ok:
                return r.reason
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
            "checks": {r.name: {"ok": r.ok, "reason": r.reason, "detail": r.detail} for r in self.results},
        }


def internal_error_readiness() -> LedgerReadiness:
    """Fallback used by atlas.main's lifespan when check_ledger_storage()
    itself raises something this module did not anticipate - the same
    second, outer safety net check_snapshots()'s own
    internal_error_readiness() provides, never a relaxation of the "no
    check here may fail startup" contract."""
    return LedgerReadiness(tuple(
        LedgerCheckResult(
            name, False, REASON_INTERNAL_ERROR,
            "ledger readiness check failed unexpectedly at startup - see server logs",
        )
        for name in LEDGER_CHECK_NAMES
    ))


def check_ledger_storage(directory: Optional[Path]) -> tuple[LedgerReadiness, Optional[LedgerStores]]:
    """Pure aside from file I/O - safe to call at startup, and directly
    testable against a tmp_path fixture.

    directory=None means "treat as unconfigured for this environment" (see
    Settings.resolved_research_ledger_dir()) - no filesystem operation of
    any kind is attempted, and stores=None is returned, since there is no
    path to construct LedgerStores against. Callers (the research_pipeline
    router) already gate on readiness before touching stores, so a None
    here is never a surprise - see atlas.api.deps.get_ledger_stores's own
    docstring.

    For any real Path, LedgerStores is always constructed (even on a
    degraded readiness) - store construction is side-effect-free (each
    store class just holds a Path; nothing touches disk until a caller
    actually reads or writes through one), so a genuinely broken directory
    surfaces its own real, observable error at the point of actual use,
    never masked behind a None."""
    results: list[LedgerCheckResult] = []

    if directory is None:
        results.append(LedgerCheckResult(
            "configuration_valid", False, REASON_NOT_CONFIGURED,
            "RESEARCH_LEDGER_DIR is not set - refusing to fall back to an implicit, possibly-ephemeral "
            "path outside development",
        ))
        results.extend(
            LedgerCheckResult(name, False, REASON_SKIPPED, "skipped - configuration_valid failed")
            for name in LEDGER_CHECK_NAMES if name != "configuration_valid"
        )
        return LedgerReadiness(tuple(results)), None

    directory_str = str(directory).strip()
    config_valid = bool(directory_str) and directory_str != "."
    results.append(
        LedgerCheckResult(
            "configuration_valid", config_valid,
            None if config_valid else REASON_BLANK_PATH,
            None if config_valid else "RESEARCH_LEDGER_DIR resolves to a blank path",
        )
    )

    directory_ready = False
    if config_valid:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            results.append(LedgerCheckResult("ledger_directory", True, None, None))
            directory_ready = True
        except OSError:
            results.append(
                LedgerCheckResult("ledger_directory", False, REASON_DIRECTORY_NOT_CREATABLE, "directory could not be created")
            )
    else:
        results.append(LedgerCheckResult("ledger_directory", False, REASON_SKIPPED, "skipped - configuration_valid failed"))

    writable = False
    if directory_ready:
        sentinel = directory / ".startup_check"
        try:
            sentinel.write_text("ok", encoding="utf-8")
            sentinel.unlink()
            results.append(LedgerCheckResult("volume_mounted", True, None, None))
            writable = True
        except OSError:
            results.append(LedgerCheckResult("volume_mounted", False, REASON_NOT_WRITABLE, "directory is not writable"))
    else:
        results.append(LedgerCheckResult("volume_mounted", False, REASON_SKIPPED, "skipped - ledger_directory failed"))

    stores = _build_stores(directory)
    results.append(LedgerCheckResult("jsonl_stores_initialized", True, None, None))

    if writable:
        try:
            for store in stores.all_stores():
                store.all()
            results.append(LedgerCheckResult("registries_available", True, None, None))
        except Exception:
            results.append(
                LedgerCheckResult(
                    "registries_available", False, REASON_REGISTRIES_UNREADABLE,
                    "one or more registries could not be read",
                )
            )
    else:
        results.append(
            LedgerCheckResult("registries_available", False, REASON_SKIPPED, "skipped - volume_mounted failed")
        )

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
        suffix = f" ({result.reason}: {result.detail})" if result.detail and not result.ok else ""
        lines.append(f"{mark} {label}{suffix}")
    lines.append("✓ API mounted")
    lines.append(f"✓ Environment: {environment}")
    outcome = "completed" if readiness.status == "ready" else "completed with degraded ledger storage"
    lines.append(f"Startup {outcome} in {elapsed_ms:.0f} ms")
    return "\n".join(lines)
