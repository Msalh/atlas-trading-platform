"""
UI v2. Orchestrates a full research-snapshot export: re-runs RE-1's and
RE-2's already-frozen, already-certified pipelines against the same frozen
five-file CSV dataset that produced research/RE1_*.md / RE2_*.md, and the
existing certifier script's own certify() function, then serializes each
result via serialization.py.

Reproduction, not new computation: build_statistical_profile() and
build_setup_profiling_dataset() are pure functions of (states, config,
generated_at, source_description) - calling them again with the exact
values already published in the checked-in markdown reports reproduces
the exact same payload, byte for byte (see the reproducibility test in
tests/test_research_export_snapshot_builder.py). RE1_GENERATED_AT /
RE2_GENERATED_AT below are those exact, already-published values, reused
rather than a fresh datetime.now() - this is what makes `payload`
genuinely deterministic across export runs: the ONLY wall-clock-dependent
value anywhere in a snapshot file is envelope.exported_at, which is never
part of the checksum input.

Single-pass requirement (amendment 7): build_setup_profiling_dataset() is
called exactly once per export and its result passed to all six of RE-2's
build_* functions - never re-run per report. RE-1's build_statistical_profile()
already computes its whole result in one call internally, so no equivalent
risk exists there.

One correction discovered by running this module for real (not a design
guess): RunManifest.code_version is computed INTERNALLY by
build_statistical_profile()/build_run_manifest() via
atlas.research.service.current_code_version() (git rev-parse HEAD) at
CALL TIME - it is not a parameter either function accepts. A fresh
re-run therefore embeds WHATEVER commit is current when the export
script happens to run, not the historical commit RE-1/RE-2 were actually
frozen at - which would silently break payload reproducibility every
time any commit lands anywhere in the repo, unrelated to RE-1/RE-2
entirely. Since neither function can be changed to accept an override
(that would modify RE-1/RE-2's frozen code), this module corrects the
OUTPUT after the fact via dataclasses.replace() - substituting a stable,
hardcoded historical commit hash (the same one already published in the
checked-in RE1_*.md/RE2_*.md "Code version" lines) onto the already-built,
otherwise-unmodified result. This changes no computation, only a
metadata field on a fresh copy of the output.

certify()'s own internal load-and-merge pass is a genuinely separate,
unavoidable third pass: it computes certification properties (OHLC
consistency, gap classification, duplicate/conflict audit) that neither
RE-1's nor RE-2's own report objects expose. dataset-health's segment_count
is NOT recomputed a fourth time - it reuses RE-2's already-built dataset
object's own segment list directly.
"""
import dataclasses
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_LIVE_DIR = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _LIVE_DIR / "scripts"
_DATA_DIR = _LIVE_DIR.parent / "data"

sys.path.insert(0, str(_SCRIPTS_DIR))
sys.path.insert(0, str(_LIVE_DIR))

import certify_historical_dataset as certifier  # noqa: E402
import run_statistical_profile as re1_runner  # noqa: E402

from atlas.core.primitives import Symbol, Timeframe  # noqa: E402
from atlas.profiling.models import ProfilingRunConfig  # noqa: E402
from atlas.research.service import current_code_version  # noqa: E402
from atlas.research.statistical_profiling.service import build_statistical_profile  # noqa: E402
from atlas.research.setup_profiling import service as re2_service  # noqa: E402
from atlas.research_export.models import (  # noqa: E402
    SCHEMA_VERSION,
    CertificationCheckResult,
    CertificationSummary,
    DateRange,
    DatasetHealthPayload,
    DatasetIdentity,
    SnapshotEnvelope,
)
from atlas.research_export.known_warnings import KNOWN_BASELINE_WARNINGS  # noqa: E402
from atlas.research_export.serialization import content_checksum, to_jsonable  # noqa: E402

SYMBOL = "MNQ1!"
TIMEFRAME = "5m"
CADENCE_MINUTES = 5

FROZEN_DATASET_CSV_PATHS: tuple[str, ...] = (
    str(_DATA_DIR / "CME_03_03_25_16_06_25.csv"),
    str(_DATA_DIR / "CME_16_06_25_30_09_25.csv"),
    str(_DATA_DIR / "CME_01_10_31_12.csv"),
    str(_DATA_DIR / "CME_01_01_05_04.csv"),
    str(_DATA_DIR / "CME_06_04_20_07.csv"),
)

# The exact generated_at values already published in the checked-in
# research/RE1_Fact_Profile.md and research/RE2_Setup_Profile.md headers -
# reused (never datetime.now()) so every RE-1/RE-2 report payload,
# including its own embedded RunManifest.generated_at, is byte-for-byte
# reproducible across export runs.
RE1_GENERATED_AT = datetime.fromisoformat("2026-07-20T12:55:24.093399+00:00")
RE2_GENERATED_AT = datetime.fromisoformat("2026-07-20T14:18:36.013255+00:00")

# The exact "Code version" already published in the same two report
# headers - see the module docstring for why this must be a stable
# constant rather than re-derived via current_code_version() on every
# export run.
RE1_SOURCE_COMPUTATION_VERSION = "a907325fbb357097fb0e8e064d46772e2b719964"
RE2_SOURCE_COMPUTATION_VERSION = "806e4f1ae2386a68207192089ab303d77c05fa66"
# docs/market_engine/re1-5file-phase3-certification-report.md's own
# "Tool" line names this as the certifier's commit at certification time.
DATASET_HEALTH_SOURCE_COMPUTATION_VERSION = "a907325fbb357097fb0e8e064d46772e2b719964"

RE1_REPORT_FILENAMES: tuple[str, ...] = (
    "RE1_Fact_Profile.md", "RE1_RuleRelationships.md", "RE1_ConditionalProbability.md",
    "RE1_TimeDistribution.md", "RE1_Persistence.md",
)
RE2_REPORT_FILENAMES: tuple[str, ...] = (
    "RE2_Setup_Profile.md", "RE2_Time_Distribution.md", "RE2_Clustering.md",
    "RE2_Setup_Overlap.md", "RE2_Context_Profile.md", "RE2_Setup_Transitions.md",
)

RE1_FREEZE_DOC = "docs/market_engine/re1-phase5-freeze.md"
RE2_FREEZE_DOC = "docs/market_engine/re2-freeze.md"
DATASET_HEALTH_FREEZE_DOC = "docs/market_engine/re1-5file-phase3-certification-report.md"


def _source_description() -> str:
    return "csv:" + ",".join(FROZEN_DATASET_CSV_PATHS)


def _load_frozen_states():
    states, _per_file_counts, _merge_stats = re1_runner.load_and_merge_states(
        list(FROZEN_DATASET_CSV_PATHS), SYMBOL, TIMEFRAME, CADENCE_MINUTES,
    )
    return sorted(states, key=lambda s: s.envelope.occurred_at)


def _profiling_run_config(ordered) -> ProfilingRunConfig:
    return ProfilingRunConfig(
        symbol=Symbol(SYMBOL), timeframe=Timeframe(TIMEFRAME),
        start=ordered[0].envelope.occurred_at, end=ordered[-1].envelope.occurred_at,
        limit=len(ordered),
    )


def _dataset_identity_from_manifest(manifest, row_count: int) -> DatasetIdentity:
    return DatasetIdentity(
        symbol=manifest.symbol, timeframe=manifest.timeframe, row_count=row_count,
        date_range=DateRange(start=manifest.requested_start, end=manifest.requested_end),
    )


def _build_envelope(
    *, source_computation_version, source_freeze_document: str,
    report_filenames: tuple[str, ...], payload: dict, dataset_identity: DatasetIdentity,
    exported_at: datetime,
) -> SnapshotEnvelope:
    return SnapshotEnvelope(
        schema_version=SCHEMA_VERSION,
        source_computation_version=source_computation_version,
        snapshot_exporter_version=current_code_version(),
        source_freeze_document=source_freeze_document,
        source_report_versions={name: source_computation_version for name in report_filenames},
        content_checksum=content_checksum(payload),
        exported_at=exported_at.astimezone(timezone.utc).isoformat(),
        dataset_identity=dataset_identity,
    )


def build_re1_snapshot(exported_at: datetime) -> dict:
    ordered = _load_frozen_states()
    config = _profiling_run_config(ordered)
    profile = build_statistical_profile(ordered, config, RE1_GENERATED_AT, _source_description())

    # See module docstring: current_code_version() inside
    # build_statistical_profile() reflects whatever HEAD is current right
    # now, not the historical freeze commit - corrected here on a fresh
    # copy of the (otherwise unmodified) output, never on RE-1 itself.
    fixed_manifest = dataclasses.replace(profile.manifest, code_version=RE1_SOURCE_COMPUTATION_VERSION)
    profile = dataclasses.replace(profile, manifest=fixed_manifest)

    payload = to_jsonable(profile)
    dataset_identity = _dataset_identity_from_manifest(profile.manifest, len(ordered))
    envelope = _build_envelope(
        source_computation_version=RE1_SOURCE_COMPUTATION_VERSION,
        source_freeze_document=RE1_FREEZE_DOC, report_filenames=RE1_REPORT_FILENAMES,
        payload=payload, dataset_identity=dataset_identity, exported_at=exported_at,
    )
    return {"envelope": to_jsonable(envelope), "payload": payload}


def _summarize_transitions(transitions) -> dict:
    """SetupTransitions.transitions is the RAW per-episode transition list
    (16,279 entries on the real frozen dataset - ~6.3MB of JSON on its
    own). architecture doc §3.5 only asks Research Overview's transition
    panel for the matrix, recurrence rates, and the by-session breakdown -
    the aggregate view RE2_Setup_Transitions.md itself renders, never the
    raw list. Omitting it here is an editorial choice about what belongs
    in a lightweight dashboard summary snapshot, not a computation change
    or a loss of the underlying data (it remains fully available by
    re-running scripts/run_setup_profile.py, exactly as before). A count
    is kept so the UI can still report "N total transitions" without the
    full array."""
    return {
        "manifest": to_jsonable(transitions.manifest),
        "matrix": to_jsonable(transitions.matrix),
        "same_setup_recurrence_rate": to_jsonable(transitions.same_setup_recurrence_rate),
        "cross_setup_recurrence_rate": to_jsonable(transitions.cross_setup_recurrence_rate),
        "by_session": to_jsonable(transitions.by_session),
        "raw_transition_count": len(transitions.transitions),
    }


def build_re2_snapshot(exported_at: datetime) -> dict:
    ordered = _load_frozen_states()
    config = _profiling_run_config(ordered)

    # Amendment 7: build the aligned Rule/Setup profiling substrate exactly
    # once, reused for every report below - never re-run per report.
    dataset = re2_service.build_setup_profiling_dataset(ordered, config)
    manifest = re2_service.build_run_manifest(config, len(ordered), RE2_GENERATED_AT, _source_description())
    manifest = dataclasses.replace(manifest, code_version=RE2_SOURCE_COMPUTATION_VERSION)

    payload = {
        "setup_profile": to_jsonable(re2_service.build_setup_profile(dataset, manifest)),
        "time_distribution": to_jsonable(re2_service.build_time_distribution(dataset, manifest)),
        "clustering": to_jsonable(re2_service.build_clustering(dataset, manifest)),
        "overlap": to_jsonable(re2_service.build_overlap(dataset, manifest)),
        "context_profile": to_jsonable(re2_service.build_context_profile(dataset, manifest)),
        "transitions": _summarize_transitions(re2_service.build_transitions(dataset, manifest)),
    }
    dataset_identity = _dataset_identity_from_manifest(manifest, len(ordered))
    envelope = _build_envelope(
        source_computation_version=RE2_SOURCE_COMPUTATION_VERSION,
        source_freeze_document=RE2_FREEZE_DOC, report_filenames=RE2_REPORT_FILENAMES,
        payload=payload, dataset_identity=dataset_identity, exported_at=exported_at,
    )
    return {"envelope": to_jsonable(envelope), "payload": payload}, dataset


def build_dataset_health_snapshot(exported_at: datetime, re2_dataset) -> dict:
    """`re2_dataset` is the SAME object build_re2_snapshot() already built -
    segment_count is read from it directly (len(dataset.segments)), not
    recomputed via a fourth independent segment_by_gap pass. certify()'s
    own internal load/merge pass is a genuinely separate, unavoidable
    pass - it computes properties (OHLC consistency, duplicate/conflict
    audit, gap classification) neither RE-1's nor RE-2's own report
    objects expose."""
    cadence = Timeframe(TIMEFRAME).duration_minutes
    results = certifier.certify(list(FROZEN_DATASET_CSV_PATHS), SYMBOL, TIMEFRAME, cadence)

    checks = tuple(CertificationCheckResult(r.section, r.check, r.verdict, r.detail) for r in results)
    fail_count = sum(1 for r in results if r.verdict == certifier.FAIL)
    warning_count = sum(1 for r in results if r.verdict == certifier.WARNING)
    pass_count = sum(1 for r in results if r.verdict == certifier.PASS)
    verdict = "rejected" if fail_count else ("certified_with_warnings" if warning_count else "certified")
    certification = CertificationSummary(
        checks_run=len(results), pass_count=pass_count, warning_count=warning_count,
        fail_count=fail_count, verdict=verdict, checks=checks,
    )

    # Row count/date range read directly from the already-built RE-2
    # dataset's own segments - no fourth independent CSV load.
    row_count = sum(len(segment.states) for segment in re2_dataset.segments)
    first_state = re2_dataset.segments[0].states[0]
    last_state = re2_dataset.segments[-1].states[-1]
    dataset_identity = DatasetIdentity(
        symbol=SYMBOL, timeframe=TIMEFRAME, row_count=row_count,
        date_range=DateRange(
            start=first_state.envelope.occurred_at.isoformat(), end=last_state.envelope.occurred_at.isoformat(),
        ),
    )

    payload_obj = DatasetHealthPayload(
        dataset_identity=dataset_identity,
        files=tuple(os.path.basename(p) for p in FROZEN_DATASET_CSV_PATHS),
        segment_count=len(re2_dataset.segments),
        certification=certification,
        known_warnings=KNOWN_BASELINE_WARNINGS,
        warnings_source="manual_transcription",
    )
    payload = to_jsonable(payload_obj)
    envelope = _build_envelope(
        source_computation_version=DATASET_HEALTH_SOURCE_COMPUTATION_VERSION,
        source_freeze_document=DATASET_HEALTH_FREEZE_DOC, report_filenames=(),
        payload=payload, dataset_identity=dataset_identity, exported_at=exported_at,
    )
    return {"envelope": to_jsonable(envelope), "payload": payload}


def build_all_snapshots(exported_at: datetime) -> dict[str, dict]:
    re1_snapshot = build_re1_snapshot(exported_at)
    re2_snapshot, re2_dataset = build_re2_snapshot(exported_at)
    dataset_health_snapshot = build_dataset_health_snapshot(exported_at, re2_dataset)
    return {
        "re1-summary.v1.json": re1_snapshot,
        "re2-summary.v1.json": re2_snapshot,
        "dataset-health.v1.json": dataset_health_snapshot,
    }
