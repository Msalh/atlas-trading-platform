"""
UI v2, amendment 8. Hand-curated, typed, traceable transcription of the
disclosed limitations already stated in prose in
docs/market_engine/re1-phase5-freeze.md and re2-freeze.md's own "Known
limitations" sections - these documents have no dataclass source (they
are freeze-sprint close-out prose), so this is a one-time, reviewed
transcription, not a mechanically-derived figure. `warnings_source` on
the assembled DatasetHealthPayload (models.py) marks this plainly so no
consumer mistakes a transcribed warning for a computed one.

Deduplicated across both freeze documents where the same underlying fact
is stated in both (e.g. the trend_1m/certification-REJECTED fact appears
in both RE-1's and RE-2's own "Known limitations" - one entry here, not
two) - each entry's source_document points to the document judged the
most authoritative statement of that fact.
"""
from atlas.research_export.models import KnownWarning

_RE1_FREEZE = "docs/market_engine/re1-phase5-freeze.md"
_RE2_FREEZE = "docs/market_engine/re2-freeze.md"

KNOWN_BASELINE_WARNINGS: tuple[KnownWarning, ...] = (
    KnownWarning(
        id="trend-1m-lookback-limit",
        severity="warning",
        title="trend_1m unreliable before 2025-07-20",
        detail=(
            "A TradingView 1-minute-data lookback boundary (~365 days before the export date), not a "
            "pipeline defect. Does not affect any RE-1 report - trend_1m is a raw wire field, never read "
            "by the 7 registered Rule Engine facts."
        ),
        source_document=_RE1_FREEZE,
        source_section="Known limitations, item 1",
    ),
    KnownWarning(
        id="certification-verdict-rejected",
        severity="fail",
        title="Certification verdict is REJECTED",
        detail=(
            "The merged five-file dataset's formal certifier verdict is REJECTED (one FAIL: trend_1m), "
            "per this project's strict-AND certification rule, which is deliberately not weakened. RE-1 "
            "and RE-2's own reports remain valid because that FAIL sits entirely outside both packages' "
            "scope (trend_1m is read by neither) - see the certification report's own disposition section "
            "for the full reasoning."
        ),
        source_document=_RE1_FREEZE,
        source_section="Known limitations, item 2",
    ),
    KnownWarning(
        id="no-tick-size-roll-registry",
        severity="warning",
        title="No per-instrument tick-size/roll registry",
        detail="A global TICK_SIZE=0.25 constant - standing architectural debt from before RE-1/RE-2, unchanged.",
        source_document=_RE1_FREEZE,
        source_section="Known limitations, item 3",
    ),
    KnownWarning(
        id="no-contract-roll-detection",
        severity="warning",
        title="No independent contract-roll detection",
        detail=(
            "MNQ1! is TradingView's own continuous-contract construction; no discontinuity was found at "
            "any file boundary, but this project cannot independently confirm individual roll dates."
        ),
        source_document=_RE1_FREEZE,
        source_section="Known limitations, item 4",
    ),
    KnownWarning(
        id="symbol-timeframe-cli-asserted",
        severity="warning",
        title="Symbol/timeframe are CLI-asserted, not extracted from the data",
        detail="TradingView's chart-export carries no symbol column - established since Sprint 29A.6, unchanged.",
        source_document=_RE1_FREEZE,
        source_section="Known limitations, item 5",
    ),
    KnownWarning(
        id="runmanifest-package-coupling",
        severity="warning",
        title="RE-2 imports RunManifest read-only from RE-1",
        detail=(
            "A minor package coupling (RE-2 depends on a sibling research package rather than a shared "
            "base module) - disclosed as debt, not refactored, since RE-1's frozen core is never modified "
            "or moved."
        ),
        source_document=_RE2_FREEZE,
        source_section="Known limitations, item 1",
    ),
    KnownWarning(
        id="volume-ratio-null-cluster",
        severity="warning",
        title="Unresolved 18-bar volume_ratio-null cluster",
        detail=(
            "Appears in every volume_spike-dependent setup's computability breakdown, distinct from the "
            "already-explained 39-bar ATR-warmup cluster. No root cause established. A targeted, "
            "unresolved follow-up required before RE-3 depends on precise volume_spike computability "
            "counts - does not block RE-2 or the UI v2 dashboard, since RE-2's own reports already "
            "surface the count transparently."
        ),
        source_document=_RE2_FREEZE,
        source_section="Known limitations, item 2",
    ),
)

KNOWN_BASELINE_WARNING_IDS: frozenset[str] = frozenset(w.id for w in KNOWN_BASELINE_WARNINGS)


def _validate() -> None:
    ids = [w.id for w in KNOWN_BASELINE_WARNINGS]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise ValueError(f"KNOWN_BASELINE_WARNINGS contains duplicate id(s): {duplicates}")
    for w in KNOWN_BASELINE_WARNINGS:
        if w.severity not in {"warning", "fail"}:
            raise ValueError(f"{w.id}: severity must be 'warning' or 'fail', got {w.severity!r}")


_validate()
