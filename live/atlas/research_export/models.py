"""
UI v2. Data shapes for the frozen research-snapshot export - kept entirely
outside atlas.research.statistical_profiling (RE-1) and
atlas.research.setup_profiling (RE-2), per architecture doc §5.

SnapshotEnvelope separates two kinds of provenance that a single ambiguous
"code_version" field previously conflated: source_computation_version (the
RE-1/RE-2 commit that computed the figures - what the dashboard's FROZEN
BASELINE badge shows) and snapshot_exporter_version (the commit of THIS
package that merely serialized them to JSON). content_checksum covers only
the deterministic payload, never exported_at - see serialization.py's
canonical_json()/checksum functions and snapshot_builder.py for how the
split is actually computed and enforced.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Optional

SCHEMA_VERSION = "1.0"


def _frozen_mapping(source: Mapping) -> MappingProxyType:
    return MappingProxyType(dict(source))


@dataclass(frozen=True)
class DateRange:
    start: str
    end: str


@dataclass(frozen=True)
class DatasetIdentity:
    symbol: str
    timeframe: str
    row_count: int
    date_range: DateRange


@dataclass(frozen=True)
class SnapshotEnvelope:
    """Every checked-in research/snapshots/*.json file's top-level
    "envelope" key. `exported_at` is the ONLY field here expected to differ
    between two exports of the same frozen inputs - everything else is
    either a fact about the frozen computation (stable) or the export
    tooling's own version (changes only when atlas/research_export/ itself
    changes, independently of the research figures)."""

    schema_version: str
    source_computation_version: Optional[str]
    snapshot_exporter_version: Optional[str]
    source_freeze_document: str
    source_report_versions: Mapping[str, Optional[str]]
    content_checksum: str
    exported_at: str
    dataset_identity: DatasetIdentity

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_report_versions", _frozen_mapping(self.source_report_versions))


@dataclass(frozen=True)
class KnownWarning:
    """One manually-curated, typed, traceable entry in a frozen baseline's
    disclosed limitations - amendment 8. Kept outside RE-1/RE-2 (their own
    freeze documents are prose, not a dataclass source) but no longer a
    bare {severity, title, detail} shape: `id` makes a warning's presence
    or absence testable (see known_warnings.py's coverage test), and
    `source_document`/`source_section` make every entry traceable back to
    the exact prose it transcribes."""

    id: str
    severity: str  # "warning" | "fail"
    title: str
    detail: str
    source_document: str
    source_section: str


@dataclass(frozen=True)
class CertificationCheckResult:
    """Mirrors scripts/certify_historical_dataset.py's own
    CertificationResult shape field-for-field - not re-derived, just
    reused as a serialization target so certify()'s real output can be
    passed straight through to_jsonable() unchanged."""

    section: str
    check: str
    verdict: str
    detail: str


@dataclass(frozen=True)
class CertificationSummary:
    checks_run: int
    pass_count: int
    warning_count: int
    fail_count: int
    verdict: str
    checks: tuple[CertificationCheckResult, ...]


@dataclass(frozen=True)
class DatasetHealthPayload:
    """The deterministic payload half of dataset-health.v1.json - the
    envelope (provenance, checksum, exported_at) is assembled separately
    by snapshot_builder.py, exactly like the RE-1/RE-2 report payloads."""

    dataset_identity: DatasetIdentity
    files: tuple[str, ...]
    segment_count: int
    certification: CertificationSummary
    known_warnings: tuple[KnownWarning, ...]
    warnings_source: str  # "manual_transcription" - see known_warnings.py
