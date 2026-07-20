"""
Sprint 25B. Historical CSV importer Proof of Concept - reads one TradingView
chart-export CSV (produced by pine/MNQU6_market_state_v1_historical_export.pine)
and feeds it through the SAME production translation/persistence path live
webhook ingestion already uses. Reuses
atlas.market_engine.adapters.tradingview.wire_models.TradingViewMarketStatePayload.model_validate(),
atlas.market_engine.adapters.tradingview.translator.to_canonical(), and
atlas.market_engine.service.ingest_tradingview_payload() (which itself chains
the previous two plus MarketStateRepository.ingest()) completely unchanged.
Never recomputes ATR, VWAP, session boundaries, reference levels, trend,
liquidity selection, tick validation, or duplicate handling - every one of
those stays exactly where it already lives (Pine, or the existing translator/
repository). The only new logic here is the small, closed, exhaustively-
enumerated decode tables approved in Sprint 25A.6 (trend/session_name/
nearest_liquidity_type/trading_date) - a controlled, minimal exception, not a
second implementation of anything Pine already computes.

PoC scope only (Sprint 25B) - validates roughly 500-1000 bars from one export
file. Not the production bulk-backfill tool: no batching across multiple
files, no resume checkpoints, no parallelism. That is explicitly deferred to
whatever Sprint actually builds the production system on top of this proof.

Three modes:
  --inspect FILE.csv
      Reads the CSV, prints detected headers, sample rows, an inferred
      timestamp format, and null/empty-cell behavior. Builds no payloads,
      opens no database connection. Use this FIRST against a real export -
      Sprint 25A.6 explicitly could not verify TradingView's exact CSV
      column-naming/timestamp/empty-cell conventions from outside a real
      TradingView session; this mode is where that gets confirmed.

  FILE.csv --symbol MNQ1! --timeframe 5m --assume-bar-open-time
      Dry run (the default - no --apply flag). For every row, builds a
      TradingViewMarketStatePayload (Pydantic validation) and calls
      to_canonical() (domain/tick validation) - the same two steps
      ingest_tradingview_payload() itself performs before ever touching a
      repository. Never calls MarketStateRepository.ingest() and never
      requires DATABASE_URL. Reports valid/skipped/malformed counts.

  FILE.csv --symbol MNQ1! --timeframe 5m --assume-bar-open-time --apply
      Everything dry run does, plus actually calls
      ingest_tradingview_payload() (unchanged) against a real
      PostgresMarketStateRepository - requires DATABASE_URL. Reports
      inserted vs. duplicate counts in addition to the dry-run counts.
      Idempotent and safe to re-run: a second run against the same file
      reports every row as a duplicate, not a new insert - this falls
      entirely out of MarketStateRepository's existing
      UNIQUE(symbol, timeframe, event_id) behavior, not new logic here.

Rows are always processed in ascending timestamp order regardless of the
CSV's own row order (Sprint 25B scope item 3) - storage itself is
order-independent (MarketStateRepository.get_range sorts at read time), but
chronological processing keeps failure diagnosis predictable.

A single malformed or unparseable row is skipped and reported with its row
number and reason - it never aborts the run. The one thing that DOES abort
immediately, before any row is processed, is a genuinely missing REQUIRED
column (time/open/high/low/close) - a structural defect in the export
itself, not a per-row data problem.

Usage:
    python scripts/import_historical_market_state_csv.py --inspect export.csv
    python scripts/import_historical_market_state_csv.py export.csv --symbol MNQ1! --timeframe 5m --assume-bar-open-time
    DATABASE_URL=postgres://... python scripts/import_historical_market_state_csv.py \\
        export.csv --symbol MNQ1! --timeframe 5m --assume-bar-open-time --apply
"""
import argparse
import asyncio
import csv
import json
import os
import sys
from datetime import date, datetime, timezone
from typing import Any, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pydantic import ValidationError  # noqa: E402

from atlas.core.errors import AtlasDomainError  # noqa: E402
from atlas.core.primitives import Symbol, Timeframe  # noqa: E402
from atlas.market_engine.adapters.tradingview.translator import to_canonical  # noqa: E402
from atlas.market_engine.adapters.tradingview.wire_models import TradingViewMarketStatePayload  # noqa: E402
from atlas.market_engine.ports import IngestOutcome  # noqa: E402
from atlas.market_engine.service import ingest_tradingview_payload  # noqa: E402

SCHEMA_VERSION = "1.0"
SOURCE = "tradingview"
EVENT_TYPE = "bar_closed"
BAR_STATUS = "closed"

# Sprint 25A.6-approved, exhaustive against
# pine/MNQU6_market_state_v1_historical_export.pine's own f_trendCode/
# sessionNameCode/f_liquidityTypeCode helpers - must never drift from those
# independently; a change to either side needs the other updated in the same
# change, the same "keep two things in sync deliberately, test it" discipline
# already used for docs/market_engine/rule-fact-inventory.md's fact hierarchy.
_TREND_DECODE: dict[int, str] = {1: "up", 0: "flat", -1: "down"}
_SESSION_NAME_DECODE: dict[int, str] = {1: "RTH", 0: "OVERNIGHT"}
_LIQUIDITY_TYPE_DECODE: dict[int, str] = {
    1: "previous_day_high", 2: "previous_day_low",
    3: "overnight_high", 4: "overnight_low", 5: "rth_open",
}

# Sprint 25A.6: TradingView's exact export header text is unverified from
# this session. Matched case-insensitively after normalization
# (_normalize_header) against every alias listed - add an alias here rather
# than assuming a single exact spelling.
_HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "time": ("time", "timestamp", "date"),
    "open": ("open",),
    "high": ("high",),
    "low": ("low",),
    "close": ("close",),
    "volume": ("volume",),
    "export_rth_open": ("export_rth_open", "rth_open"),
    "export_previous_day_high": ("export_previous_day_high", "previous_day_high"),
    "export_previous_day_low": ("export_previous_day_low", "previous_day_low"),
    "export_overnight_high": ("export_overnight_high", "overnight_high"),
    "export_overnight_low": ("export_overnight_low", "overnight_low"),
    "export_vwap": ("export_vwap", "vwap"),
    "export_distance_from_vwap_points": ("export_distance_from_vwap_points", "distance_from_vwap_points"),
    "export_atr": ("export_atr", "atr"),
    "export_volume_ratio": ("export_volume_ratio", "volume_ratio"),
    "export_nearest_liquidity_level": ("export_nearest_liquidity_level", "nearest_liquidity_level"),
    "export_distance_to_liquidity_ticks": ("export_distance_to_liquidity_ticks", "distance_to_liquidity_ticks"),
    "export_is_rth": ("export_is_rth", "is_rth"),
    "export_trading_date": ("export_trading_date", "trading_date"),
    "export_session_name": ("export_session_name", "session_name"),
    "export_nearest_liquidity_type": ("export_nearest_liquidity_type", "nearest_liquidity_type"),
    "export_trend_1m": ("export_trend_1m", "trend_1m"),
    "export_trend_5m": ("export_trend_5m", "trend_5m"),
    "export_trend_15m": ("export_trend_15m", "trend_15m"),
    "export_trend_1h": ("export_trend_1h", "trend_1h"),
}

_REQUIRED_CANONICAL_COLUMNS = ("time", "open", "high", "low", "close")


class ImporterInputError(Exception):
    """Raised for a structural defect in the CSV itself (a required column
    missing entirely) - distinct from a single bad row, which is skipped and
    reported instead of raising."""


def _normalize_header(raw: str) -> str:
    return raw.strip().lower().replace(" ", "_").replace(".", "_").replace("-", "_")


def _build_column_map(headers: list[str], strict: bool) -> dict[str, Optional[str]]:
    """Maps each canonical field name to the actual header text found in the
    CSV, or None if not present. Raises ImporterInputError (strict=True
    only) if any of _REQUIRED_CANONICAL_COLUMNS is missing - a structural
    defect that should stop the run before any row is processed."""
    normalized_to_actual = {_normalize_header(h): h for h in headers}
    column_map: dict[str, Optional[str]] = {}
    for canonical, aliases in _HEADER_ALIASES.items():
        found = None
        for alias in aliases:
            actual = normalized_to_actual.get(_normalize_header(alias))
            if actual is not None:
                found = actual
                break
        column_map[canonical] = found

    if strict:
        missing_required = [c for c in _REQUIRED_CANONICAL_COLUMNS if column_map.get(c) is None]
        if missing_required:
            raise ImporterInputError(
                f"required column(s) not found in CSV header: {missing_required} "
                f"(detected headers: {headers}) - this is a structural defect, "
                f"not a per-row problem; the run cannot proceed"
            )
    return column_map


def _is_empty(raw: Optional[str]) -> bool:
    return raw is None or raw.strip() == "" or raw.strip().upper() in ("NAN", "NA", "NULL")


def _parse_optional_float(raw: Optional[str]) -> Optional[float]:
    if _is_empty(raw):
        return None
    return float(raw)


def _parse_timestamp(raw: str, cadence_minutes: Optional[int] = None) -> datetime:
    """Accepts either an ISO-8601 string or a Unix epoch number (seconds or
    milliseconds, distinguished by magnitude) - TradingView's exact export
    timestamp format was not verified from this session (Sprint 25A.6/25B),
    so this parser is deliberately flexible rather than assuming one shape.
    `cadence_minutes`, when given, shifts the parsed time forward by one bar
    - use this only if a real export's "time" column turns out to represent
    bar OPEN rather than bar CLOSE (Pine's own convention, via time_close);
    confirm which is true via the verification workflow's field-by-field
    comparison against live-collected data before assuming either way."""
    raw = raw.strip()
    try:
        numeric = float(raw)
    except ValueError:
        numeric = None

    if numeric is not None:
        if numeric > 1e12:
            numeric /= 1000
        parsed = datetime.fromtimestamp(numeric, tz=timezone.utc)
    else:
        normalized = raw.replace("Z", "+00:00") if raw.endswith("Z") else raw
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        parsed = parsed.astimezone(timezone.utc)

    if cadence_minutes:
        from datetime import timedelta
        parsed = parsed + timedelta(minutes=cadence_minutes)
    return parsed


def _format_iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _decode_trend(raw: Optional[str]) -> Optional[str]:
    if _is_empty(raw):
        return None
    code = int(float(raw))
    if code not in _TREND_DECODE:
        raise ValueError(f"trend code {code!r} is not one of {sorted(_TREND_DECODE)}")
    return _TREND_DECODE[code]


def _decode_session_name(raw: Optional[str]) -> Optional[str]:
    if _is_empty(raw):
        return None
    code = int(float(raw))
    if code not in _SESSION_NAME_DECODE:
        raise ValueError(f"session_name code {code!r} is not one of {sorted(_SESSION_NAME_DECODE)}")
    return _SESSION_NAME_DECODE[code]


def _decode_liquidity_type(raw: Optional[str]) -> Optional[str]:
    if _is_empty(raw):
        return None
    code = int(float(raw))
    if code not in _LIQUIDITY_TYPE_DECODE:
        raise ValueError(f"nearest_liquidity_type code {code!r} is not one of {sorted(_LIQUIDITY_TYPE_DECODE)}")
    return _LIQUIDITY_TYPE_DECODE[code]


def _decode_trading_date(raw: Optional[str]) -> Optional[str]:
    if _is_empty(raw):
        return None
    value = int(float(raw))
    year, remainder = divmod(value, 10000)
    month, day = divmod(remainder, 100)
    try:
        return date(year, month, day).isoformat()
    except ValueError as e:
        raise ValueError(f"trading_date {raw!r} does not decode to a valid calendar date") from e


def _decode_bool(raw: Optional[str]) -> Optional[bool]:
    if _is_empty(raw):
        return None
    return bool(int(float(raw)))


def _cell(row: dict[str, str], column_map: dict[str, Optional[str]], canonical: str) -> Optional[str]:
    header = column_map.get(canonical)
    if header is None:
        return None
    return row.get(header)


def row_to_raw_json(
    row: dict[str, str], column_map: dict[str, Optional[str]],
    symbol: str, timeframe: str, cadence_minutes: Optional[int] = None,
) -> dict[str, Any]:
    """Pure. Builds a raw wire-shaped dict from one CSV row - the ONLY new
    logic in this file: reading already-exported values and decoding the
    Sprint 25A.6 enum tables, never recomputing anything Pine already
    computed. Raises ValueError with a clear reason if the row can't be
    parsed into a candidate payload at all (bad enum code, bad timestamp,
    bad trading_date) - the caller treats this as a "skipped" row, distinct
    from a row that parses fine but fails real Pydantic/translator
    validation ("malformed")."""
    occurred_at = _parse_timestamp(_cell(row, column_map, "time"), cadence_minutes)
    timestamp_str = _format_iso(occurred_at)
    event_id = f"{symbol}:{timeframe}:{timestamp_str}"

    return {
        "schema_version": SCHEMA_VERSION,
        "event_id": event_id,
        "symbol": symbol,
        "source": SOURCE,
        "timeframe": timeframe,
        "timestamp": timestamp_str,
        "bar_status": BAR_STATUS,
        "event_type": EVENT_TYPE,
        "open": _parse_optional_float(_cell(row, column_map, "open")),
        "high": _parse_optional_float(_cell(row, column_map, "high")),
        "low": _parse_optional_float(_cell(row, column_map, "low")),
        "close": _parse_optional_float(_cell(row, column_map, "close")),
        "volume": _parse_optional_float(_cell(row, column_map, "volume")),
        "session_name": _decode_session_name(_cell(row, column_map, "export_session_name")),
        "is_rth": _decode_bool(_cell(row, column_map, "export_is_rth")),
        "trading_date": _decode_trading_date(_cell(row, column_map, "export_trading_date")),
        "rth_open": _parse_optional_float(_cell(row, column_map, "export_rth_open")),
        "previous_day_high": _parse_optional_float(_cell(row, column_map, "export_previous_day_high")),
        "previous_day_low": _parse_optional_float(_cell(row, column_map, "export_previous_day_low")),
        "overnight_high": _parse_optional_float(_cell(row, column_map, "export_overnight_high")),
        "overnight_low": _parse_optional_float(_cell(row, column_map, "export_overnight_low")),
        "vwap": _parse_optional_float(_cell(row, column_map, "export_vwap")),
        "distance_from_vwap_points": _parse_optional_float(_cell(row, column_map, "export_distance_from_vwap_points")),
        "atr": _parse_optional_float(_cell(row, column_map, "export_atr")),
        "volume_ratio": _parse_optional_float(_cell(row, column_map, "export_volume_ratio")),
        "nearest_liquidity_level": _parse_optional_float(_cell(row, column_map, "export_nearest_liquidity_level")),
        "nearest_liquidity_type": _decode_liquidity_type(_cell(row, column_map, "export_nearest_liquidity_type")),
        "distance_to_liquidity_ticks": _parse_optional_float(_cell(row, column_map, "export_distance_to_liquidity_ticks")),
        "overnight_high_status": None,
        "overnight_low_status": None,
        "previous_day_high_status": None,
        "previous_day_low_status": None,
        "trend_1m": _decode_trend(_cell(row, column_map, "export_trend_1m")),
        "trend_5m": _decode_trend(_cell(row, column_map, "export_trend_5m")),
        "trend_15m": _decode_trend(_cell(row, column_map, "export_trend_15m")),
        "trend_1h": _decode_trend(_cell(row, column_map, "export_trend_1h")),
        "liquidity_sweep": False,
        "reclaim": False,
        "rejection": False,
        "displacement": False,
        "volume_spike": False,
    }


async def _validate_only(raw_json: dict[str, Any]) -> Optional[str]:
    """Dry-run path: the same two steps ingest_tradingview_payload() itself
    performs before ever calling repository.ingest() - Pydantic validation,
    then domain/tick translation. Returns None on success, an error string
    on failure. Never touches a repository."""
    try:
        payload = TradingViewMarketStatePayload.model_validate(raw_json)
    except ValidationError as e:
        return f"invalid payload: {e.errors(include_context=False)}"
    try:
        to_canonical(payload)
    except AtlasDomainError as e:
        return str(e)
    return None


def _inspect(csv_path: str) -> None:
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        sample_rows = []
        for i, row in enumerate(reader):
            if i >= 5:
                break
            sample_rows.append(row)

    print(f"File: {csv_path}")
    print(f"\nDetected headers ({len(headers)}):")
    for h in headers:
        print(f"  {h!r}  (normalized: {_normalize_header(h)!r})")

    print(f"\nSample rows (first {len(sample_rows)}):")
    for row in sample_rows:
        print(f"  {row}")

    column_map = _build_column_map(headers, strict=False)
    print("\nColumn coverage against expected fields:")
    for canonical in _HEADER_ALIASES:
        header = column_map.get(canonical)
        required = " (REQUIRED)" if canonical in _REQUIRED_CANONICAL_COLUMNS else ""
        if header is not None:
            print(f"  {canonical}: FOUND -> {header!r}{required}")
        else:
            print(f"  {canonical}: MISSING{required}")

    if sample_rows:
        time_header = column_map.get("time")
        if time_header is not None:
            sample_time = sample_rows[0].get(time_header, "")
            print(f"\nSample time value: {sample_time!r}")
            try:
                parsed = _parse_timestamp(sample_time)
                print(f"  Parses as: {parsed.isoformat()}")
                print(
                    "  NOT independently confirmed whether this represents bar OPEN or "
                    "bar CLOSE - compare against a known live-collected bar's occurred_at "
                    "before trusting this (see --assume-bar-open-time)."
                )
            except Exception as e:  # noqa: BLE001 - inspect mode reports, never crashes
                print(f"  Could NOT parse as a timestamp: {e}")

        empties = sorted({k for row in sample_rows for k, v in row.items() if _is_empty(v)})
        print(f"\nColumns with at least one empty/NA-looking cell in the sample: {empties}")


def build_candidates(
    raw_rows: list[dict[str, str]], column_map: dict[str, Optional[str]],
    symbol: str, timeframe: str, cadence_minutes: Optional[int] = None,
) -> tuple[list[tuple[int, datetime, dict[str, Any]]], list[tuple[int, str]]]:
    """Pure. Returns (candidates, skipped) - candidates sorted chronologically
    regardless of the CSV's own row order (Sprint 25B scope item 3). A row
    that can't even be parsed into a raw payload dict (bad enum code, bad
    timestamp) is skipped and reported, never fatal to the whole file."""
    skipped: list[tuple[int, str]] = []
    candidates: list[tuple[int, datetime, dict[str, Any]]] = []
    for row_number, row in enumerate(raw_rows, start=2):  # header is row 1
        try:
            raw_json = row_to_raw_json(row, column_map, symbol, timeframe, cadence_minutes)
            occurred_at = datetime.fromisoformat(raw_json["timestamp"].replace("Z", "+00:00"))
        except (ValueError, KeyError) as e:
            skipped.append((row_number, str(e)))
            continue
        candidates.append((row_number, occurred_at, raw_json))
    candidates.sort(key=lambda item: item[1])
    return candidates, skipped


async def process_candidates(
    candidates: list[tuple[int, datetime, dict[str, Any]]], repository: Any, apply_writes: bool,
) -> tuple[int, int, int, list[tuple[int, str]]]:
    """The core per-row loop, independent of where `repository` came from -
    real Postgres in production use, InMemoryMarketStateRepository in tests.
    Returns (valid_count, inserted_count, duplicate_count, malformed)."""
    valid_count = 0
    inserted_count = 0
    duplicate_count = 0
    malformed: list[tuple[int, str]] = []

    for row_number, _occurred_at, raw_json in candidates:
        if not apply_writes:
            error = await _validate_only(raw_json)
            if error is not None:
                malformed.append((row_number, error))
            else:
                valid_count += 1
            continue

        result = await ingest_tradingview_payload(raw_json, json.dumps(raw_json), repository)
        if result.error is not None:
            malformed.append((row_number, result.error))
            continue
        valid_count += 1
        if result.outcome == IngestOutcome.DUPLICATE:
            duplicate_count += 1
        else:
            inserted_count += 1

    return valid_count, inserted_count, duplicate_count, malformed


async def _run_import(csv_path: str, symbol: str, timeframe: str, apply_writes: bool, assume_bar_open_time: bool) -> None:
    symbol_obj = Symbol(symbol)  # validates non-blank
    timeframe_obj = Timeframe(timeframe)  # raises ValueError if not one of 1m/5m/15m/1h
    cadence_minutes = timeframe_obj.duration_minutes if assume_bar_open_time else None

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        column_map = _build_column_map(headers, strict=True)
        raw_rows = list(reader)

    candidates, skipped = build_candidates(raw_rows, column_map, symbol_obj.ticker, timeframe_obj.value, cadence_minutes)

    pool = None
    repository = None
    if apply_writes:
        if not os.environ.get("DATABASE_URL"):
            raise SystemExit("DATABASE_URL is not set - required for --apply. Omit --apply for a dry run.")
        from atlas.db import create_pool
        from atlas.market_engine.repositories.postgres import PostgresMarketStateRepository
        pool = await create_pool()
        repository = PostgresMarketStateRepository(pool)

    try:
        valid_count, inserted_count, duplicate_count, malformed = await process_candidates(candidates, repository, apply_writes)
    finally:
        if pool is not None:
            await pool.close()

    print(f"File: {csv_path}")
    print(f"Mode: {'APPLY (wrote to database)' if apply_writes else 'DRY RUN (no writes)'}")
    print(f"Total data rows: {len(raw_rows)}")
    print(f"Skipped (could not parse row): {len(skipped)}")
    print(f"Malformed (failed validation/translation): {len(malformed)}")
    print(f"Valid: {valid_count}")
    if apply_writes:
        print(f"  Inserted: {inserted_count}")
        print(f"  Duplicate: {duplicate_count}")

    if skipped:
        print("\nSkipped rows:")
        for row_number, reason in skipped:
            print(f"  row {row_number}: {reason}")
    if malformed:
        print("\nMalformed rows:")
        for row_number, reason in malformed:
            print(f"  row {row_number}: {reason}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("csv_path", help="Path to a TradingView chart-export CSV")
    parser.add_argument("--symbol", help="e.g. MNQ1! - the confirmed live production symbol (Sprint 31 Task 1); required unless --inspect")
    parser.add_argument("--timeframe", help="e.g. 5m (required unless --inspect)")
    parser.add_argument("--inspect", action="store_true", help="Inspect the CSV only - no payloads, no DB")
    parser.add_argument("--apply", action="store_true", help="Actually write to the database (default: dry run)")
    parser.add_argument(
        "--assume-bar-open-time", action="store_true",
        help="Shift the CSV's time column forward by one bar's cadence before use - TradingView's "
             "native chart-export 'time' column is bar OPEN time (platform default), while the live "
             "webhook uses bar CLOSE time (Pine's time_close) - confirmed by real field-by-field "
             "comparison, Sprint 31 Task 3 (docs/market_engine/sprint31-task3-equivalence-report.md). "
             "Required for MNQ1!/5m historical CSV imports; for a different export, confirm via the "
             "same comparison workflow before assuming either way.",
    )
    args = parser.parse_args()

    if args.inspect:
        _inspect(args.csv_path)
        return

    if not args.symbol or not args.timeframe:
        parser.error("--symbol and --timeframe are required outside --inspect mode")

    try:
        asyncio.run(_run_import(args.csv_path, args.symbol, args.timeframe, args.apply, args.assume_bar_open_time))
    except ImporterInputError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
