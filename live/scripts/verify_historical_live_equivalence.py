"""
Sprint 31 Task 3 - Historical vs Live Equivalence certification utility.

Compares a fresh historical CSV export (the format
scripts/import_historical_market_state_csv.py already parses) against real
production MarketState data retrieved via the existing
GET /api/v1/market-state/export?start=T&end=T exact-timestamp lookup (Task 3
- no new endpoint was added for this; start == end against the existing
/export route already returns exactly one event).

Reuses the CSV column-mapping/decode logic from
import_historical_market_state_csv.py completely unchanged - this tool never
re-derives how a CSV row becomes a raw wire-shaped dict. The historical side
is then run through the SAME TradingViewMarketStatePayload.model_validate()
+ to_canonical() + market_state_to_dict() pipeline production itself uses,
so this compares two REAL canonical MarketState shapes, not raw CSV text
against raw JSON - proving the full historical pipeline (CSV -> importer ->
translator -> canonical) produces the same result as the full live pipeline
(webhook -> translator -> canonical -> repository -> read API).

Read-only, no network access, no database connection. It only reads a local
CSV file plus JSON files already saved from real GET /export responses (the
curl commands from Task 2/3 - production access happens there, not here,
deliberately keeping credentials out of this script).

Usage:
    python scripts/verify_historical_live_equivalence.py \\
        --csv fresh_export.csv --symbol MNQ1! --timeframe 5m \\
        --api-response 2026-07-20T07:50:00Z=export_0750.json \\
        --api-response 2026-07-20T08:00:00Z=export_0800.json \\
        --api-response 2026-07-20T08:10:00Z=export_0810.json

Each --api-response value is TIMESTAMP=PATH, where PATH is the saved JSON
body of one GET /market-state/export?...&start=TIMESTAMP&end=TIMESTAMP
response. Its "data" array must contain exactly one element (the same
exact-timestamp lookup Task 3 already established).
"""
import argparse
import csv
import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import import_historical_market_state_csv as importer  # noqa: E402

from atlas.market_engine.adapters.tradingview.translator import to_canonical  # noqa: E402
from atlas.market_engine.adapters.tradingview.wire_models import TradingViewMarketStatePayload  # noqa: E402
from atlas.market_engine.service import market_state_to_dict  # noqa: E402

# Display order matches the field list specified for Sprint 31 Task 3
# certification exactly.
FIELD_LABELS: dict[str, str] = {
    "open": "Open",
    "high": "High",
    "low": "Low",
    "close": "Close",
    "vwap": "VWAP",
    "atr": "ATR",
    "volume": "Volume",
    "volume_ratio": "Volume Ratio",
    "distance_from_vwap_points": "Distance From VWAP",
    "nearest_liquidity_level": "Nearest Liquidity Level",
    "nearest_liquidity_type": "Nearest Liquidity Type",
    "trend_1m": "Trend 1m",
    "trend_5m": "Trend 5m",
    "trend_15m": "Trend 15m",
    "trend_1h": "Trend 1h",
    "liquidity_sweep": "Liquidity Sweep",
    "reclaim": "Reclaim",
    "rejection": "Rejection",
    "displacement": "Displacement",
    "volume_spike": "Volume Spike",
}

# Sent as a hardcoded false by BOTH the live and historical Pine paths, by
# deliberate Sprint 5 design (pine/MNQU6_market_state_v1.pine's own
# docstring: "Deliberately NOT implemented in this Sprint... sent as
# explicit false/null, not fabricated, not omitted"). A match on these five
# proves the hardcoded-false convention still holds identically on both
# sides, not that translation is field-accurate for them - flagged in the
# report so a trivial pass here is never over-read as strong evidence.
TRIVIALLY_CONSTANT_FIELDS = frozenset({
    "liquidity_sweep", "reclaim", "rejection", "displacement", "volume_spike",
})


@dataclass(frozen=True)
class FieldComparison:
    field: str
    label: str
    historical_value: Any
    live_value: Any
    passed: bool
    trivially_constant: bool


def compare_fields(historical: dict[str, Any], live: dict[str, Any]) -> list[FieldComparison]:
    """Pure. Exact equality only - no tolerance. Per Sprint 29A.6's own
    standard for this proof ('not approximately, exactly'), a benign
    floating-point representation difference between a CSV-parsed value and
    a JSON-parsed value is exactly the kind of thing this comparison exists
    to catch, not something to paper over with an epsilon."""
    results = []
    for field, label in FIELD_LABELS.items():
        h = historical.get(field)
        v = live.get(field)
        results.append(FieldComparison(
            field=field, label=label, historical_value=h, live_value=v,
            passed=(h == v), trivially_constant=field in TRIVIALLY_CONSTANT_FIELDS,
        ))
    return results


def historical_state_at(
    csv_path: str, symbol: str, timeframe: str, target_timestamp: str,
    cadence_minutes: Optional[int] = None,
) -> Optional[dict[str, Any]]:
    """Finds the one CSV row matching `target_timestamp` and runs it through
    the real production translation pipeline - not a re-implementation of
    to_canonical, the actual function.

    `cadence_minutes`: passed straight through to the importer's own
    build_candidates/row_to_raw_json - the exact same bar-open-to-bar-close
    shift import_historical_market_state_csv.py's --assume-bar-open-time
    flag already applies, not a second implementation of it. Only pass this
    once real evidence (an actual field-by-field comparison against live
    data) has confirmed the CSV's native "time" column is bar-open, not
    bar-close - never speculatively, and never silently."""
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        column_map = importer._build_column_map(headers, strict=True)
        raw_rows = list(reader)

    candidates, _skipped = importer.build_candidates(raw_rows, column_map, symbol, timeframe, cadence_minutes)
    for _row_number, occurred_at, raw_json in candidates:
        if raw_json["timestamp"] == target_timestamp or occurred_at.isoformat() == target_timestamp.replace("Z", "+00:00"):
            payload = TradingViewMarketStatePayload.model_validate(raw_json)
            state = to_canonical(payload)
            return market_state_to_dict(state)
    return None


def live_state_from_export_response(response_path: str) -> Optional[dict[str, Any]]:
    """Reads a saved GET /market-state/export JSON body and returns its one
    event - the endpoint's own existing shape (market_state_to_dict), read
    verbatim, nothing recomputed here."""
    with open(response_path, encoding="utf-8") as f:
        body = json.load(f)
    data = body.get("data", [])
    if len(data) != 1:
        raise ValueError(
            f"{response_path!r} has {len(data)} events in 'data' - expected exactly 1 "
            f"(a start==end exact-timestamp export response)"
        )
    return data[0]


def render_report(results_by_timestamp: dict[str, list[FieldComparison]]) -> str:
    lines = ["Sprint 31 Task 3 - Historical vs Live Equivalence Certification", "=" * 64, ""]
    overall_pass = True
    for timestamp, results in results_by_timestamp.items():
        lines.append(f"Timestamp: {timestamp}")
        lines.append("-" * 64)
        for r in results:
            mark = "PASS" if r.passed else "FAIL"
            note = "  (trivially-constant field, see report notes)" if r.trivially_constant else ""
            lines.append(f"  [{mark}] {r.label:<24} historical={r.historical_value!r:<20} live={r.live_value!r}{note}")
            if not r.passed:
                overall_pass = False
        lines.append("")

    lines.append("=" * 64)
    if overall_pass:
        lines.append("Task 3 - Historical <-> Live Equivalence: PASS")
    else:
        lines.append("Task 3 - Historical <-> Live Equivalence: FAIL")
        lines.append("(at least one field mismatched at least one timestamp - see above)")
    lines.append("")
    lines.append(
        "Note: Liquidity Sweep / Reclaim / Rejection / Displacement / Volume Spike are "
        "hardcoded false on both the live and historical Pine paths by design (Sprint 5) - "
        "a PASS on these five confirms that convention still holds identically on both "
        "sides, it does not independently confirm translation accuracy for them."
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--csv", required=True, help="Path to the fresh historical export CSV")
    parser.add_argument("--symbol", required=True, help="e.g. MNQ1! - must match the confirmed live symbol (Task 1)")
    parser.add_argument("--timeframe", required=True, help="e.g. 5m")
    parser.add_argument(
        "--api-response", action="append", required=True, metavar="TIMESTAMP=PATH",
        help="A saved GET /market-state/export response body for one start==end timestamp. Repeatable.",
    )
    parser.add_argument(
        "--assume-bar-open-time", action="store_true",
        help="Shift the CSV's native 'time' column forward by one bar's cadence before matching - only pass "
             "this once a real comparison has already shown a bar-open/bar-close offset (the same flag "
             "import_historical_market_state_csv.py already has, reused here, not reimplemented). Do not "
             "pass this speculatively.",
    )
    args = parser.parse_args()

    from atlas.core.primitives import Timeframe
    cadence_minutes = Timeframe(args.timeframe).duration_minutes if args.assume_bar_open_time else None

    results_by_timestamp: dict[str, list[FieldComparison]] = {}
    for entry in args.api_response:
        timestamp, _, response_path = entry.partition("=")
        if not timestamp or not response_path:
            parser.error(f"--api-response {entry!r} is not in TIMESTAMP=PATH form")

        historical = historical_state_at(args.csv, args.symbol, args.timeframe, timestamp, cadence_minutes)
        if historical is None:
            print(f"ERROR: no CSV row found for timestamp {timestamp!r} - cannot compare", file=sys.stderr)
            raise SystemExit(1)

        live = live_state_from_export_response(response_path)
        results_by_timestamp[timestamp] = compare_fields(historical, live)

    print(render_report(results_by_timestamp))


if __name__ == "__main__":
    main()
