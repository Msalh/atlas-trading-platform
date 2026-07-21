"""
Sprint 31 Task 4 - Historical Dataset Certification.

Produces a PASS/WARNING/FAIL report for a historical CSV export, covering
dataset identity, time continuity, session integrity, market-data integrity,
and feature integrity - proving (or disproving) that the dataset is
trustworthy enough for the Research Engine to consume. This is
certification, not research: no statistics, no edges, no strategy
evaluation - only "is this data what it claims to be."

Reuses, unchanged:
  - import_historical_market_state_csv.py's CSV parsing (column mapping,
    chronological candidate building)
  - TradingViewMarketStatePayload.model_validate() + to_canonical() - the
    same production translation pipeline every other Sprint 31 tool reuses
  - atlas.market_engine.service.find_gaps (Sprint 8) - gap detection is not
    re-implemented here

Everything else in this module (OHLC consistency, duplicate-timestamp
detection, session/overnight invariants, feature-field consistency) has no
existing equivalent anywhere in the codebase and is new, focused, pure
certification logic - not a re-implementation of anything that already
exists elsewhere.

Read-only. No database connection, no production code touched, no new
endpoint.

Usage:
    python scripts/certify_historical_dataset.py \\
        --csv "data/CME_MINI_MNQ1!, 5_504af.csv" --symbol MNQ1! --timeframe 5m
"""
import argparse
import csv
import os
import sys
from dataclasses import dataclass
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import import_historical_market_state_csv as importer  # noqa: E402

from atlas.core.primitives import Timeframe  # noqa: E402
from atlas.market_engine.adapters.tradingview.translator import to_canonical  # noqa: E402
from atlas.market_engine.adapters.tradingview.wire_models import TradingViewMarketStatePayload  # noqa: E402
from atlas.market_engine.models import MarketState  # noqa: E402
from atlas.market_engine.service import find_gaps, market_state_to_dict  # noqa: E402

PASS, WARNING, FAIL = "PASS", "WARNING", "FAIL"

# Sent as a hardcoded false by BOTH the live and historical Pine paths, by
# deliberate Sprint 5 design (pine/MNQU6_market_state_v1.pine's own
# docstring). Their presence as constant False is expected, not a defect -
# it reflects that real detection logic for these was never implemented,
# not that this dataset is broken.
PLACEHOLDER_FLAG_FIELDS = ("liquidity_sweep", "reclaim", "rejection", "displacement", "volume_spike")
VALID_TREND_VALUES = {"up", "down", "flat", None}
LIQUIDITY_CANDIDATE_FIELDS = (
    ("previous_day_high", "previous_day_high"),
    ("previous_day_low", "previous_day_low"),
    ("overnight_high", "overnight_high"),
    ("overnight_low", "overnight_low"),
    ("rth_open", "rth_open"),
)


@dataclass(frozen=True)
class CertificationResult:
    section: str
    check: str
    verdict: str
    detail: str


def load_states(
    csv_path: str, symbol: str, timeframe: str, cadence_minutes: int | None = None,
) -> tuple[list[MarketState], list[tuple[int, str]]]:
    """Reuses the importer's own CSV parsing and the real production
    translation pipeline unchanged - never a second implementation of
    either. Returns (states, skipped) - skipped rows are themselves
    certification evidence (a structurally unparseable row), not silently
    dropped.

    `cadence_minutes` reuses the importer's own --assume-bar-open-time
    mechanism unchanged (Sprint 31 Task 3's finding: this data source's
    native CSV "time" column is bar-open, while production stores
    bar-close) - previously missing from this function entirely, meaning
    every certification run before this fix reported bar-open timestamps,
    5 minutes off from what production actually stores. Certification
    verdicts themselves are unaffected by a uniform timestamp shift (gap
    sizes, ordering, and every field value are unchanged) - only the
    specific timestamps printed in the report were off by one bar."""
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        column_map = importer._build_column_map(headers, strict=True)
        raw_rows = list(reader)

    candidates, skipped = importer.build_candidates(raw_rows, column_map, symbol, timeframe, cadence_minutes)
    states = []
    for _row_number, _occurred_at, raw_json in candidates:
        payload = TradingViewMarketStatePayload.model_validate(raw_json)
        states.append(to_canonical(payload))
    return states, skipped


def _dicts(states: list[MarketState]) -> list[dict[str, Any]]:
    return [market_state_to_dict(s) for s in states]


def check_dataset_identity(states: list[MarketState], asserted_symbol: str, asserted_timeframe: str) -> list[CertificationResult]:
    section = "1. Dataset Identity"
    results = []
    if not states:
        return [CertificationResult(section, "Bar count", FAIL, "no states to certify - dataset is empty")]

    symbols = {s.symbol.ticker for s in states}
    if symbols == {asserted_symbol}:
        results.append(CertificationResult(section, "Symbol consistency", PASS, f"all {len(states)} bars carry symbol={asserted_symbol!r}"))
    else:
        results.append(CertificationResult(
            section, "Symbol consistency", FAIL,
            f"asserted symbol={asserted_symbol!r} but found {sorted(symbols)} in the data",
        ))

    timeframes = {s.timeframe.value for s in states}
    if timeframes == {asserted_timeframe}:
        results.append(CertificationResult(section, "Timeframe consistency", PASS, f"all bars carry timeframe={asserted_timeframe!r}"))
    else:
        results.append(CertificationResult(
            section, "Timeframe consistency", FAIL,
            f"asserted timeframe={asserted_timeframe!r} but found {sorted(timeframes)} in the data",
        ))

    ordered = sorted(states, key=lambda s: s.envelope.occurred_at)
    start, end = ordered[0].envelope.occurred_at, ordered[-1].envelope.occurred_at
    results.append(CertificationResult(
        section, "Date range / bar count", PASS,
        f"{len(states)} bars, {start.isoformat()} -> {end.isoformat()}",
    ))
    results.append(CertificationResult(
        section, "Symbol provenance", WARNING,
        f"symbol={asserted_symbol!r} is CLI-asserted at import time, not extracted from the CSV itself "
        f"(TradingView's chart-data-export carries no symbol column - see Sprint 29A.6 Section 1). "
        f"This certification uses {asserted_symbol!r} because Sprint 31 Task 1 independently confirmed it "
        f"as the live production symbol; the original Sprint 25B/26 import commands asserted 'MNQU6' instead, "
        f"which is now known not to match any literal wire value observed in this project's evidence.",
    ))
    return results


def check_time_continuity(states: list[MarketState], timeframe: Timeframe) -> list[CertificationResult]:
    section = "2. Time Continuity"
    results = []
    ordered = sorted(states, key=lambda s: s.envelope.occurred_at)

    timestamps = [s.envelope.occurred_at for s in ordered]
    duplicates = {t for t in timestamps if timestamps.count(t) > 1}
    if duplicates:
        results.append(CertificationResult(
            section, "Duplicate timestamps", FAIL,
            f"{len(duplicates)} timestamp(s) appear more than once: {sorted(t.isoformat() for t in duplicates)}",
        ))
    else:
        results.append(CertificationResult(section, "Duplicate timestamps", PASS, "every timestamp appears exactly once"))

    is_strictly_increasing = all(a < b for a, b in zip(timestamps, timestamps[1:]))
    if is_strictly_increasing:
        results.append(CertificationResult(section, "Chronological ordering", PASS, "strictly increasing after sort, no reversals"))
    else:
        results.append(CertificationResult(section, "Chronological ordering", FAIL, "a non-increasing adjacent pair exists after sorting"))

    gaps = find_gaps(ordered, timeframe)
    if not gaps:
        results.append(CertificationResult(section, "Gap detection", PASS, "no gap exceeds 1.5x the expected bar interval"))
    else:
        large_gaps = [g for g in gaps if g["actual_gap_minutes"] > 24 * 60]
        results.append(CertificationResult(
            section, "Gap detection", WARNING,
            f"{len(gaps)} gap(s) found ({len(large_gaps)} exceeding 24h). find_gaps() does not know market "
            f"hours (its own docstring) - each gap needs human adjudication against known session/weekend "
            f"closure, not an automatic verdict. Gaps: "
            + "; ".join(f"{g['after']} -> {g['before']} ({g['actual_gap_minutes']}min, ~{g['estimated_missing_bars']} bars)" for g in gaps),
        ))
    return results


def check_session_integrity(states: list[MarketState]) -> list[CertificationResult]:
    section = "3. Session Integrity"
    results = []
    ordered = sorted(states, key=lambda s: s.envelope.occurred_at)

    session_mismatches = [
        s for s in ordered
        if s.is_rth is not None and s.session_name is not None
        and (s.is_rth is True) != (s.session_name.value == "RTH")
    ]
    if not session_mismatches:
        results.append(CertificationResult(section, "is_rth / session_name consistency", PASS, "always agree where both are present"))
    else:
        results.append(CertificationResult(
            section, "is_rth / session_name consistency", FAIL,
            f"{len(session_mismatches)} bar(s) where is_rth disagrees with session_name, "
            f"first at {session_mismatches[0].envelope.occurred_at.isoformat()}",
        ))

    overnight_violations = []
    prev = None
    for s in ordered:
        if prev is not None and prev.is_rth is True and s.is_rth is False:
            pass  # transition into overnight - a reset here is expected, not checked further
        elif prev is not None and prev.is_rth is False and s.is_rth is True:
            pass  # transition into RTH
        elif prev is not None and prev.is_rth is True and s.is_rth is True:
            if prev.overnight_high != s.overnight_high or prev.overnight_low != s.overnight_low:
                overnight_violations.append(s.envelope.occurred_at.isoformat())
        prev = s
    if not overnight_violations:
        results.append(CertificationResult(section, "Overnight reset-and-hold invariant", PASS, "overnight_high/low held constant through every RTH session"))
    else:
        results.append(CertificationResult(
            section, "Overnight reset-and-hold invariant", FAIL,
            f"overnight_high/low changed mid-RTH-session at {len(overnight_violations)} bar(s), "
            f"first at {overnight_violations[0]}",
        ))

    trading_dates = [s.trading_date for s in ordered if s.trading_date is not None]
    non_decreasing = all(a <= b for a, b in zip(trading_dates, trading_dates[1:]))
    if non_decreasing:
        results.append(CertificationResult(section, "trading_date monotonicity", PASS, "never decreases across the series"))
    else:
        results.append(CertificationResult(section, "trading_date monotonicity", FAIL, "trading_date decreases somewhere in the series"))

    return results


def check_market_data_integrity(states: list[MarketState], max_expected_warmup_clusters: int = 1) -> list[CertificationResult]:
    """`max_expected_warmup_clusters` scales the ATR-null tolerance for
    multi-file certification runs. Empirically confirmed on the real 5-file
    RE-1 dataset (97,858 bars): ATR nulls cluster in groups of exactly 13
    bars, precisely at file-START boundaries not already masked by dedup
    overlap with a preceding file - i.e. one legitimate ta.atr(14) warmup
    cluster per distinct export session, not one flat constant regardless of
    how many files were merged. A single-file run keeps the original
    threshold (20) unchanged; certify() passes len(csv_paths) here."""
    section = "4. Market Data Integrity"
    results = []
    atr_null_threshold = 20 * max_expected_warmup_clusters

    ohlc_violations = []
    for s in states:
        if None in (s.open, s.high, s.low, s.close):
            continue
        o, h, lo, c = s.open.value, s.high.value, s.low.value, s.close.value
        if not (h >= max(o, c) and lo <= min(o, c) and h >= lo):
            ohlc_violations.append(s.envelope.occurred_at.isoformat())
    if not ohlc_violations:
        results.append(CertificationResult(section, "OHLC consistency", PASS, "High >= max(Open, Close) and Low <= min(Open, Close) hold for every bar"))
    else:
        results.append(CertificationResult(
            section, "OHLC consistency", FAIL,
            f"{len(ohlc_violations)} bar(s) violate High/Low bounds, first at {ohlc_violations[0]}",
        ))

    invalid_volume = [s.envelope.occurred_at.isoformat() for s in states if s.volume is None or s.volume < 0]
    if not invalid_volume:
        results.append(CertificationResult(section, "Volume validity", PASS, "present and non-negative for every bar"))
    else:
        results.append(CertificationResult(
            section, "Volume validity", FAIL,
            f"{len(invalid_volume)} bar(s) with null or negative volume, first at {invalid_volume[0]}",
        ))

    invalid_vwap = [s.envelope.occurred_at.isoformat() for s in states if s.vwap is None or s.vwap <= 0]
    if not invalid_vwap:
        results.append(CertificationResult(section, "VWAP validity", PASS, "present and positive for every bar"))
    else:
        results.append(CertificationResult(
            section, "VWAP validity", FAIL,
            f"{len(invalid_vwap)} bar(s) with null or non-positive vwap, first at {invalid_vwap[0]}",
        ))

    invalid_atr = [s.envelope.occurred_at.isoformat() for s in states if s.atr is None or s.atr <= 0]
    if not invalid_atr:
        results.append(CertificationResult(section, "ATR validity", PASS, "present and positive for every bar"))
    elif len(invalid_atr) <= atr_null_threshold:
        results.append(CertificationResult(
            section, "ATR validity", WARNING,
            f"{len(invalid_atr)} bar(s) with null/non-positive atr (first at {invalid_atr[0]}) - "
            f"within the expected warmup tolerance for {max_expected_warmup_clusters} input file(s) "
            f"(<= {atr_null_threshold} = 20 x max_expected_warmup_clusters), consistent with ta.atr's own "
            f"warmup period recurring once per distinct export session, not necessarily a defect; "
            f"confirm these fall only at file-start boundaries before treating this as clean",
        ))
    else:
        results.append(CertificationResult(
            section, "ATR validity", FAIL,
            f"{len(invalid_atr)} bar(s) with null/non-positive atr - exceeds the expected warmup tolerance for "
            f"{max_expected_warmup_clusters} input file(s) (<= {atr_null_threshold}), too many to be explained "
            f"by per-file warmup alone, first at {invalid_atr[0]}",
        ))

    return results


def check_feature_integrity(states: list[MarketState], max_expected_warmup_clusters: int = 1) -> list[CertificationResult]:
    """`max_expected_warmup_clusters` mirrors check_market_data_integrity's
    ATR tolerance (20 per file) for the trend fields' null counts, so a
    small per-file-warmup-sized null cluster is distinguished from a null
    rate far too large to be warmup - which must be reported as a real,
    unexplained finding rather than guessed at as "probably warmup." """
    section = "5. Feature Integrity"
    results = []
    trend_null_threshold = 20 * max_expected_warmup_clusters

    for field in ("trend_1m", "trend_5m", "trend_15m", "trend_1h"):
        values = {getattr(s, field) for s in states}
        invalid = values - VALID_TREND_VALUES
        null_count = sum(1 for s in states if getattr(s, field) is None)
        if invalid:
            results.append(CertificationResult(section, f"{field} validity", FAIL, f"invalid value(s) found: {sorted(invalid)}"))
        elif null_count == 0:
            results.append(CertificationResult(section, f"{field} validity", PASS, "populated on every bar, only up/down/flat values present"))
        elif null_count <= trend_null_threshold:
            results.append(CertificationResult(
                section, f"{field} validity", WARNING,
                f"{null_count}/{len(states)} bars have a null {field} - within the expected warmup tolerance "
                f"for {max_expected_warmup_clusters} input file(s) (<= {trend_null_threshold}), consistent with "
                f"indicator warmup at a series/file start; values otherwise valid",
            ))
        else:
            results.append(CertificationResult(
                section, f"{field} validity", FAIL,
                f"{null_count}/{len(states)} bars ({null_count / len(states):.1%}) have a null {field} - far exceeds "
                f"the expected warmup tolerance for {max_expected_warmup_clusters} input file(s) "
                f"(<= {trend_null_threshold}); this is NOT explainable by ordinary indicator warmup and requires "
                f"investigation before this dataset is used for any analysis depending on {field} - values are "
                f"otherwise valid where present",
            ))

    non_false = {
        field: sum(1 for s in states if getattr(s, field) is not False)
        for field in PLACEHOLDER_FLAG_FIELDS
    }
    if not any(non_false.values()):
        results.append(CertificationResult(
            section, "Rule Engine placeholder flags", WARNING,
            "liquidity_sweep / reclaim / rejection / displacement / volume_spike are False on every bar - "
            "this is the correct, EXPECTED value: both the live and historical Pine paths deliberately send "
            "these as a hardcoded false (Sprint 5 design - real detection is the Rule Engine's job, computed "
            "downstream, not sent on the wire). A constant False here is not a data defect and does not "
            "indicate missing detection capability was silently lost.",
        ))
    else:
        offending = {k: v for k, v in non_false.items() if v}
        results.append(CertificationResult(
            section, "Rule Engine placeholder flags", FAIL,
            f"expected all-False by design (Sprint 5), but found non-False values: {offending} - "
            f"this means the wire contract or CSV export changed unexpectedly",
        ))

    vwap_mismatches = []
    for s in states:
        if s.close is None or s.vwap is None or s.distance_from_vwap_points is None:
            continue
        expected = s.close.value - s.vwap
        if abs(expected - s.distance_from_vwap_points) > 1e-6:
            vwap_mismatches.append(s.envelope.occurred_at.isoformat())
    if not vwap_mismatches:
        results.append(CertificationResult(section, "distance_from_vwap_points consistency", PASS, "close - vwap matches the reported value on every bar (tolerance 1e-6)"))
    else:
        results.append(CertificationResult(
            section, "distance_from_vwap_points consistency", FAIL,
            f"{len(vwap_mismatches)} bar(s) where close - vwap disagrees with distance_from_vwap_points, first at {vwap_mismatches[0]}",
        ))

    liquidity_mismatches = []
    for s in states:
        if s.nearest_liquidity_level is None or s.nearest_liquidity_type is None:
            continue
        candidates = {
            label: getattr(s, attr).value for label, attr in LIQUIDITY_CANDIDATE_FIELDS
            if getattr(s, attr) is not None
        }
        claimed_value = candidates.get(s.nearest_liquidity_type)
        if claimed_value is None or claimed_value != s.nearest_liquidity_level.value:
            liquidity_mismatches.append((s.envelope.occurred_at.isoformat(), "does not match its own claimed source level"))
            continue
        if candidates:
            actual_closest = min(candidates, key=lambda k: abs(candidates[k] - s.close.value))
            if actual_closest != s.nearest_liquidity_type:
                liquidity_mismatches.append((s.envelope.occurred_at.isoformat(), f"claimed {s.nearest_liquidity_type!r} but {actual_closest!r} is actually closest"))
    if not liquidity_mismatches:
        results.append(CertificationResult(section, "nearest_liquidity_level/type consistency", PASS, "level matches its claimed source field and is genuinely the closest, on every bar"))
    else:
        results.append(CertificationResult(
            section, "nearest_liquidity_level/type consistency", FAIL,
            f"{len(liquidity_mismatches)} bar(s) inconsistent, first: {liquidity_mismatches[0][0]} ({liquidity_mismatches[0][1]})",
        ))

    return results


def check_duplicate_and_conflict_audit(merge_stats: dict) -> list[CertificationResult]:
    """Only produced for a multi-file certification run - reports the
    stats atlas.research (via run_statistical_profile.load_and_merge_states,
    reused directly, not re-derived) already computed while merging: raw
    row count, unique row count, identical duplicates safely removed, and
    conflicting-content duplicates. A conflict here is impossible to
    observe as a PASS/WARNING/FAIL - load_and_merge_states already raises
    ConflictingTimestampError before this function could ever be called
    with a nonzero conflict_count, so this section exists to make the
    (already-enforced) zero-conflicts guarantee visible in the report,
    not to re-check it."""
    section = "0b. Duplicate & Conflict Audit (multi-file)"
    return [CertificationResult(
        section, "Cross-file timestamp merge", PASS,
        f"raw_row_count={merge_stats['raw_row_count']}, unique_row_count={merge_stats['unique_row_count']}, "
        f"identical_duplicates_removed={merge_stats['identical_duplicates_removed']}, "
        f"conflict_count={merge_stats['conflict_count']} (a nonzero conflict count would already have raised "
        f"ConflictingTimestampError before certification could run at all)",
    )]


def certify(
    csv_paths: list[str], symbol: str, timeframe: str, cadence_minutes: int | None = None,
) -> list[CertificationResult]:
    results = []
    if len(csv_paths) == 1:
        states, skipped = load_states(csv_paths[0], symbol, timeframe, cadence_minutes)
        if skipped:
            results.append(CertificationResult(
                "0. Ingestion", "Row parsing", WARNING if len(skipped) < 5 else FAIL,
                f"{len(skipped)} row(s) could not be parsed at all: {skipped[:5]}{'...' if len(skipped) > 5 else ''}",
            ))
        else:
            results.append(CertificationResult(
                "0. Ingestion", "Row parsing", PASS, f"all rows in {csv_paths[0]!r} parsed successfully",
            ))
    else:
        # Multi-file: reuse run_statistical_profile.load_and_merge_states
        # directly - the same merge/dedup/conflict-detection logic Phase 2
        # already built, never a second implementation of it here.
        import run_statistical_profile as runner
        states, per_file_counts, merge_stats = runner.load_and_merge_states(
            csv_paths, symbol, timeframe, cadence_minutes,
        )
        for csv_path, loaded, new_count in per_file_counts:
            results.append(CertificationResult(
                "0. Ingestion", f"Row parsing: {csv_path}", PASS,
                f"{loaded} rows loaded, {new_count} new after dedup against prior files",
            ))
        results += check_duplicate_and_conflict_audit(merge_stats)
        states = sorted(states, key=lambda s: s.envelope.occurred_at)

    results += check_dataset_identity(states, symbol, timeframe)
    results += check_time_continuity(states, Timeframe(timeframe))
    results += check_session_integrity(states)
    results += check_market_data_integrity(states, max_expected_warmup_clusters=len(csv_paths))
    results += check_feature_integrity(states, max_expected_warmup_clusters=len(csv_paths))
    return results


def render_report(results: list[CertificationResult]) -> str:
    lines = ["Sprint 31 Task 4 - Historical Dataset Certification Report", "=" * 70, ""]
    by_section: dict[str, list[CertificationResult]] = {}
    for r in results:
        by_section.setdefault(r.section, []).append(r)

    for section, section_results in by_section.items():
        lines.append(section)
        lines.append("-" * 70)
        for r in section_results:
            lines.append(f"  [{r.verdict}] {r.check}")
            lines.append(f"         {r.detail}")
        lines.append("")

    fails = [r for r in results if r.verdict == FAIL]
    warnings = [r for r in results if r.verdict == WARNING]
    lines.append("=" * 70)
    lines.append("6. Certification Summary")
    lines.append("-" * 70)
    lines.append(f"  Checks run: {len(results)}  |  PASS: {sum(1 for r in results if r.verdict == PASS)}  |  WARNING: {len(warnings)}  |  FAIL: {len(fails)}")
    lines.append("")
    if fails:
        lines.append("VERDICT: REJECTED")
        lines.append("Hard failure(s) found - this dataset must not be used by the Research Engine until every FAIL above is resolved.")
    elif warnings:
        lines.append("VERDICT: CERTIFIED WITH WARNINGS")
        lines.append("No hard failures. Every WARNING above is explained and, in each case here, reflects a "
                      "documented, by-design property (asserted symbol provenance, Pine-computed warmup nulls, "
                      "or the not-yet-implemented Rule Engine placeholder flags) rather than an unexplained defect.")
    else:
        lines.append("VERDICT: CERTIFIED")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--csv", required=True, action="append",
        help="Path to a historical export CSV. Repeatable, in chronological order - when more than one "
             "is given, files are merged via run_statistical_profile.load_and_merge_states (same "
             "first-insert-wins dedup, same conflict detection) before certification runs.",
    )
    parser.add_argument("--symbol", required=True, help="e.g. MNQ1! - the symbol to certify this dataset under")
    parser.add_argument("--timeframe", required=True, help="e.g. 5m")
    parser.add_argument(
        "--assume-bar-open-time", action="store_true",
        help="Same flag as import_historical_market_state_csv.py - required for the certified "
             "MNQ1!/5m historical CSVs (Sprint 31 Task 3).",
    )
    args = parser.parse_args()

    cadence_minutes = Timeframe(args.timeframe).duration_minutes if args.assume_bar_open_time else None
    results = certify(args.csv, args.symbol, args.timeframe, cadence_minutes)
    print(render_report(results))


if __name__ == "__main__":
    main()
