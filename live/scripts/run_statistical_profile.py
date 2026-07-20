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

from atlas.core.primitives import Symbol, Timeframe  # noqa: E402
from atlas.market_engine.adapters.tradingview.translator import to_canonical  # noqa: E402
from atlas.market_engine.adapters.tradingview.wire_models import TradingViewMarketStatePayload  # noqa: E402
from atlas.market_engine.models import MarketState  # noqa: E402
from atlas.profiling.models import ProfilingRunConfig  # noqa: E402
from atlas.research.statistical_profiling import reports  # noqa: E402
from atlas.research.statistical_profiling.service import build_statistical_profile  # noqa: E402

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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--csv", required=True, help="Path to a historical export CSV")
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
    states = load_states_from_csv(args.csv, args.symbol, args.timeframe, cadence_minutes)
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
    source_description = f"csv:{args.csv}"

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
