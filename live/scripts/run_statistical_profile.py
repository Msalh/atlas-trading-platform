"""
Sprint RE-1 (Research Engine Phase 1). Runs the statistical profiling
pipeline (atlas.research.statistical_profiling) against a historical CSV
export and writes the five RE-1 markdown reports.

Source-agnostic core: atlas.research.statistical_profiling.service
.build_statistical_profile() takes a plain list[MarketState] and never
knows or cares whether that list came from a CSV (today) or a repository
range query (once one exists). Only THIS script's load_states_from_csv()
is CSV-specific - the exact same pipeline is designed to be re-pointed at
a much larger historical dataset later by adding a sibling loader function
(e.g. load_states_from_repository()), never by changing any analysis code
in statistical_profiling/.

Reuses import_historical_market_state_csv.py's CSV parsing and the same
production translation pipeline (TradingViewMarketStatePayload
.model_validate + to_canonical) every other Sprint 31 tool already reuses -
never a second CSV parser or a second translator.

Usage:
    python scripts/run_statistical_profile.py \\
        --csv "data/CME_MINI_MNQ1!, 5_504af.csv" --symbol MNQ1! --timeframe 5m \\
        --out research/ --validation-run
"""
import argparse
import csv
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import import_historical_market_state_csv as importer  # noqa: E402

from atlas.core.primitives import Price, Symbol, Timeframe  # noqa: E402
from atlas.market_engine.adapters.tradingview.translator import to_canonical  # noqa: E402
from atlas.market_engine.adapters.tradingview.wire_models import TradingViewMarketStatePayload  # noqa: E402
from atlas.market_engine.models import MarketState  # noqa: E402
from atlas.profiling.models import ProfilingRunConfig  # noqa: E402
from atlas.research.statistical_profiling import reports  # noqa: E402
from atlas.research.statistical_profiling.service import build_statistical_profile  # noqa: E402

# The same field set scripts/verify_historical_live_equivalence.py already
# uses for its own real/historical equivalence proof (Sprint 31 Task 3),
# reused here rather than re-derived - what "identical Market State
# content" means for conflict detection across overlapping files.
_CONFLICT_COMPARISON_FIELDS = (
    "open", "high", "low", "close", "vwap", "atr", "volume", "volume_ratio",
    "distance_from_vwap_points", "nearest_liquidity_level", "nearest_liquidity_type",
    "trend_1m", "trend_5m", "trend_15m", "trend_1h",
)


class ConflictingTimestampError(Exception):
    """Raised when the same (symbol, timeframe, event_id) appears in more
    than one input file with genuinely DIFFERENT Market State content - a
    real data conflict that must never be silently resolved by picking one
    file's version arbitrarily. An identical-content duplicate (the
    expected, safe case for two adjacent files' overlap window) is never an
    error - it is silently deduplicated, first file wins, matching
    MarketStateRepository.ingest()'s own real behavior exactly."""


def _field_value(state: MarketState, field: str):
    value = getattr(state, field)
    return value.value if isinstance(value, Price) else value

REPORT_WRITERS = {
    "RE1_Fact_Profile.md": reports.render_fact_profile_report,
    "RE1_RuleRelationships.md": reports.render_rule_relationships_report,
    "RE1_ConditionalProbability.md": reports.render_conditional_probability_report,
    "RE1_TimeDistribution.md": reports.render_time_distribution_report,
    "RE1_Persistence.md": reports.render_persistence_report,
}


def load_states_from_csv(
    csv_path: str, symbol: str, timeframe: str, cadence_minutes: int | None = None,
) -> list[MarketState]:
    """The one CSV-specific piece of this script - reuses the importer's
    own column mapping and candidate-building, then the real production
    translation pipeline unchanged, exactly like Sprint 31's other tools.
    `cadence_minutes` reuses the importer's own --assume-bar-open-time
    mechanism unchanged (Sprint 31 Task 3's finding: this dataset's native
    CSV "time" column is bar-open, while production stores bar-close)."""
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        column_map = importer._build_column_map(headers, strict=True)
        raw_rows = list(reader)

    candidates, skipped = importer.build_candidates(raw_rows, column_map, symbol, timeframe, cadence_minutes)
    if skipped:
        print(f"WARNING: {len(skipped)} row(s) could not be parsed and were skipped: {skipped[:5]}", file=sys.stderr)

    states = []
    for _row_number, _occurred_at, raw_json in candidates:
        payload = TradingViewMarketStatePayload.model_validate(raw_json)
        states.append(to_canonical(payload))
    return states


def load_and_merge_states(
    csv_paths: list[str], symbol: str, timeframe: str, cadence_minutes: int | None = None,
) -> tuple[list[MarketState], list[tuple[str, int, int]], dict]:
    """Loads each CSV in the given order and merges them, keeping the FIRST
    occurrence of any (symbol, timeframe, event_id) - matching
    MarketStateRepository.ingest()'s own real first-insert-wins dedup
    semantics exactly (UNIQUE(symbol, timeframe, event_id), Sprint 3),
    never a second, independently-invented dedup rule.

    Every timestamp seen more than once is compared field-by-field
    (_CONFLICT_COMPARISON_FIELDS) against the first-seen version. Identical
    content is a safe, silent duplicate. Any difference is a genuine
    conflict - collected, never silently resolved - and raises
    ConflictingTimestampError once every file has been scanned, so a
    single run reports every conflict found, not just the first.

    Returns (merged states, per-file (path, rows_loaded, new_rows_after_
    dedup) counts, stats dict with raw_row_count/unique_row_count/
    identical_duplicates_removed/conflict_count) - the per-file counts
    alone are enough to predict Phase B's real Inserted/Duplicate split
    before ever touching a database."""
    by_event_id: dict[str, MarketState] = {}
    per_file_counts: list[tuple[str, int, int]] = []
    conflicts: list[tuple[str, str, dict, dict]] = []
    raw_row_count = 0

    for csv_path in csv_paths:
        file_states = load_states_from_csv(csv_path, symbol, timeframe, cadence_minutes)
        raw_row_count += len(file_states)
        new_count = 0
        for state in file_states:
            event_id = state.envelope.event_id
            existing = by_event_id.get(event_id)
            if existing is None:
                by_event_id[event_id] = state
                new_count += 1
                continue
            existing_values = {f: _field_value(existing, f) for f in _CONFLICT_COMPARISON_FIELDS}
            new_values = {f: _field_value(state, f) for f in _CONFLICT_COMPARISON_FIELDS}
            if existing_values != new_values:
                conflicts.append((csv_path, event_id, existing_values, new_values))
        per_file_counts.append((csv_path, len(file_states), new_count))

    unique_row_count = len(by_event_id)
    stats = {
        "raw_row_count": raw_row_count,
        "unique_row_count": unique_row_count,
        "identical_duplicates_removed": raw_row_count - unique_row_count - len(conflicts),
        "conflict_count": len(conflicts),
    }

    if conflicts:
        lines = [f"{len(conflicts)} conflicting timestamp(s) found across the input files - refusing to silently pick one:"]
        for csv_path, event_id, existing_values, new_values in conflicts:
            diffs = {
                field: (existing_values[field], new_values[field])
                for field in _CONFLICT_COMPARISON_FIELDS
                if existing_values[field] != new_values[field]
            }
            lines.append(f"  {event_id} (conflicting version found in {csv_path}): {diffs}")
        lines.append(f"Stats so far: {stats}")
        raise ConflictingTimestampError("\n".join(lines))

    return list(by_event_id.values()), per_file_counts, stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--csv", required=True, action="append",
        help="Path to a historical export CSV. Repeatable, in chronological order - when the same "
             "(symbol, timeframe, event_id) appears in more than one file, the FIRST file given wins "
             "and later duplicates are dropped, matching MarketStateRepository.ingest()'s own real "
             "first-insert-wins dedup semantics exactly.",
    )
    parser.add_argument("--symbol", required=True, help="e.g. MNQ1!")
    parser.add_argument("--timeframe", required=True, help="e.g. 5m")
    parser.add_argument("--out", default="research", help="Output directory for the RE1_*.md reports")
    parser.add_argument(
        "--validation-run", action="store_true",
        help="Label every report as a pipeline-correctness validation run, not a market-characteristics "
             "finding - use this whenever the dataset is too small to support a real conclusion.",
    )
    parser.add_argument(
        "--assume-bar-open-time", action="store_true",
        help="Same flag as import_historical_market_state_csv.py - required for the certified "
             "MNQ1!/5m historical CSV (Sprint 31 Task 3); confirm via that same comparison workflow "
             "before using it for a different export.",
    )
    args = parser.parse_args()

    timeframe_obj = Timeframe(args.timeframe)
    cadence_minutes = timeframe_obj.duration_minutes if args.assume_bar_open_time else None

    try:
        states, per_file_counts, merge_stats = load_and_merge_states(
            args.csv, args.symbol, args.timeframe, cadence_minutes,
        )
    except ConflictingTimestampError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise SystemExit(1) from None

    for csv_path, loaded, new_count in per_file_counts:
        print(f"{csv_path}: {loaded} rows loaded, {new_count} new after dedup against prior files")
    print(
        f"Merge stats: raw_row_count={merge_stats['raw_row_count']} "
        f"unique_row_count={merge_stats['unique_row_count']} "
        f"identical_duplicates_removed={merge_stats['identical_duplicates_removed']} "
        f"conflict_count={merge_stats['conflict_count']}"
    )

    if not states:
        print("ERROR: no states loaded from CSV - nothing to profile", file=sys.stderr)
        raise SystemExit(1)

    ordered = sorted(states, key=lambda s: s.envelope.occurred_at)
    config = ProfilingRunConfig(
        symbol=Symbol(args.symbol), timeframe=timeframe_obj,
        start=ordered[0].envelope.occurred_at, end=ordered[-1].envelope.occurred_at,
        limit=len(ordered),
    )
    generated_at = datetime.now(timezone.utc)
    source_description = "csv:" + ",".join(args.csv)

    profile = build_statistical_profile(ordered, config, generated_at, source_description)

    os.makedirs(args.out, exist_ok=True)
    for filename, render in REPORT_WRITERS.items():
        content = render(profile, validation_run=args.validation_run)
        path = os.path.join(args.out, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Wrote {path} ({len(content)} chars)")

    print(
        f"\nRun complete: {profile.manifest.row_count} bars, {args.symbol}/{args.timeframe}, "
        f"{profile.manifest.requested_start} -> {profile.manifest.requested_end}"
        + (" [VALIDATION RUN]" if args.validation_run else "")
    )


if __name__ == "__main__":
    main()
