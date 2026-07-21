"""
Sprint RE-2 (Research Engine Phase 2). Runs the episode-aware Setup Engine
profiling pipeline (atlas.research.setup_profiling) against one or more
historical export CSVs and writes the six computed RE2_*.md reports.

Reuses run_statistical_profile.load_and_merge_states unchanged - the same
five-file merge/dedup/conflict-detection path RE-1 already certified, never
a second CSV-loading implementation for RE-2.

Usage:
    python scripts/run_setup_profile.py \\
        --csv "data/CME_03_03_25_16_06_25.csv" --csv "data/CME_16_06_25_30_09_25.csv" \\
        --csv "data/CME_01_10_31_12.csv" --csv "data/CME_01_01_05_04.csv" --csv "data/CME_06_04_20_07.csv" \\
        --symbol MNQ1! --timeframe 5m --assume-bar-open-time --out research/
"""
import argparse
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import run_statistical_profile as runner  # noqa: E402

from atlas.core.primitives import Symbol, Timeframe  # noqa: E402
from atlas.profiling.models import ProfilingRunConfig  # noqa: E402
from atlas.research.setup_profiling import reports, service  # noqa: E402

REPORT_WRITERS = {
    "RE2_Setup_Profile.md": (service.build_setup_profile, reports.render_setup_profile_report),
    "RE2_Time_Distribution.md": (service.build_time_distribution, reports.render_time_distribution_report),
    "RE2_Clustering.md": (service.build_clustering, reports.render_clustering_report),
    "RE2_Setup_Overlap.md": (service.build_overlap, reports.render_setup_overlap_report),
    "RE2_Context_Profile.md": (service.build_context_profile, reports.render_context_profile_report),
    "RE2_Setup_Transitions.md": (service.build_transitions, reports.render_setup_transitions_report),
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--csv", required=True, action="append",
        help="Path to a historical export CSV. Repeatable, in chronological order - merged via "
             "run_statistical_profile.load_and_merge_states (same first-insert-wins dedup, same "
             "conflict detection RE-1 already uses).",
    )
    parser.add_argument("--symbol", required=True, help="e.g. MNQ1!")
    parser.add_argument("--timeframe", required=True, help="e.g. 5m")
    parser.add_argument("--out", default="research", help="Output directory for the RE2_*.md reports")
    parser.add_argument(
        "--assume-bar-open-time", action="store_true",
        help="Same flag as import_historical_market_state_csv.py / run_statistical_profile.py - required "
             "for the certified MNQ1!/5m historical CSVs (Sprint 31 Task 3).",
    )
    args = parser.parse_args()

    timeframe_obj = Timeframe(args.timeframe)
    cadence_minutes = timeframe_obj.duration_minutes if args.assume_bar_open_time else None

    try:
        states, per_file_counts, merge_stats = runner.load_and_merge_states(
            args.csv, args.symbol, args.timeframe, cadence_minutes,
        )
    except runner.ConflictingTimestampError as e:
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

    print("Building episode-aware Setup Engine dataset (Rule Engine + Setup Engine evaluation)...")
    dataset = service.build_setup_profiling_dataset(ordered, config)
    manifest = service.build_run_manifest(config, len(ordered), generated_at, source_description)

    for name in dataset.setup_names:
        episode_count = len(dataset.episodes_by_setup[name])
        print(f"  {name}: {episode_count} episodes")

    os.makedirs(args.out, exist_ok=True)
    for filename, (builder, renderer) in REPORT_WRITERS.items():
        report = builder(dataset, manifest)
        content = renderer(report)
        path = os.path.join(args.out, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Wrote {path} ({len(content)} chars)")

    print(
        f"\nRun complete: {manifest.row_count} bars, {args.symbol}/{args.timeframe}, "
        f"{manifest.requested_start} -> {manifest.requested_end}"
    )


if __name__ == "__main__":
    main()
