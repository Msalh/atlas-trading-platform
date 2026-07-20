"""
Sprint 25B. Tests for scripts/import_historical_market_state_csv.py - the
historical CSV importer Proof of Concept. Imports the script as a module
directly (it lives under scripts/, not atlas/, matching how this project
already tests other operator scripts).
"""
import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from atlas.core.primitives import Symbol, Timeframe
from atlas.market_engine.adapters.tradingview.wire_models import TradingViewMarketStatePayload
from atlas.market_engine.repositories.memory import InMemoryMarketStateRepository

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "import_historical_market_state_csv.py"
_spec = importlib.util.spec_from_file_location("import_historical_market_state_csv", _SCRIPT_PATH)
importer = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = importer
_spec.loader.exec_module(importer)


def _headers():
    return ["time", "open", "high", "low", "close", "Volume"] + list(importer._HEADER_ALIASES.keys())[6:]


def _column_map():
    return importer._build_column_map(_headers(), strict=True)


def _row(**overrides):
    fields = {
        "time": "2026-07-01T13:00:00Z", "open": "100.00", "high": "101.00",
        "low": "99.00", "close": "100.50", "Volume": "1000",
        "export_rth_open": "", "export_previous_day_high": "", "export_previous_day_low": "",
        "export_overnight_high": "", "export_overnight_low": "", "export_vwap": "",
        "export_distance_from_vwap_points": "", "export_atr": "", "export_volume_ratio": "",
        "export_nearest_liquidity_level": "", "export_distance_to_liquidity_ticks": "",
        "export_is_rth": "", "export_trading_date": "", "export_session_name": "",
        "export_nearest_liquidity_type": "", "export_trend_1m": "", "export_trend_5m": "",
        "export_trend_15m": "", "export_trend_1h": "",
    }
    fields.update(overrides)
    return fields


class TestEnumDecoding:
    def test_trend_decodes_all_three_values(self):
        assert importer._decode_trend("1") == "up"
        assert importer._decode_trend("0") == "flat"
        assert importer._decode_trend("-1") == "down"

    def test_trend_empty_decodes_to_none(self):
        assert importer._decode_trend("") is None
        assert importer._decode_trend(None) is None

    def test_trend_invalid_code_raises(self):
        with pytest.raises(ValueError, match="trend code"):
            importer._decode_trend("99")

    def test_session_name_decodes_both_values(self):
        assert importer._decode_session_name("1") == "RTH"
        assert importer._decode_session_name("0") == "OVERNIGHT"

    def test_session_name_invalid_code_raises(self):
        with pytest.raises(ValueError, match="session_name code"):
            importer._decode_session_name("2")

    def test_liquidity_type_decodes_all_five_values(self):
        assert importer._decode_liquidity_type("1") == "previous_day_high"
        assert importer._decode_liquidity_type("2") == "previous_day_low"
        assert importer._decode_liquidity_type("3") == "overnight_high"
        assert importer._decode_liquidity_type("4") == "overnight_low"
        assert importer._decode_liquidity_type("5") == "rth_open"

    def test_liquidity_type_invalid_code_raises(self):
        with pytest.raises(ValueError, match="nearest_liquidity_type code"):
            importer._decode_liquidity_type("6")

    def test_liquidity_type_empty_decodes_to_none(self):
        assert importer._decode_liquidity_type("") is None


class TestTradingDateDecoding:
    def test_decodes_yyyymmdd_to_iso_date(self):
        assert importer._decode_trading_date("20260701") == "2026-07-01"

    def test_empty_decodes_to_none(self):
        assert importer._decode_trading_date("") is None

    def test_invalid_calendar_date_raises(self):
        with pytest.raises(ValueError, match="valid calendar date"):
            importer._decode_trading_date("20261301")  # month 13


class TestEventIdReconstruction:
    def test_matches_pine_convention(self):
        column_map = _column_map()
        raw = importer.row_to_raw_json(_row(), column_map, "MNQU6", "5m")
        assert raw["event_id"] == "MNQU6:5m:2026-07-01T13:00:00Z"

    def test_shifts_with_assume_bar_open_time(self):
        column_map = _column_map()
        raw = importer.row_to_raw_json(_row(), column_map, "MNQU6", "5m", cadence_minutes=5)
        assert raw["event_id"] == "MNQU6:5m:2026-07-01T13:05:00Z"
        assert raw["timestamp"] == "2026-07-01T13:05:00Z"


class TestNullHandling:
    def test_all_optional_fields_null_when_empty(self):
        column_map = _column_map()
        raw = importer.row_to_raw_json(_row(), column_map, "MNQU6", "5m")
        for field in (
            "rth_open", "previous_day_high", "previous_day_low", "overnight_high", "overnight_low",
            "vwap", "distance_from_vwap_points", "atr", "volume_ratio", "nearest_liquidity_level",
            "distance_to_liquidity_ticks", "is_rth", "trading_date", "session_name",
            "nearest_liquidity_type", "trend_1m", "trend_5m", "trend_15m", "trend_1h",
        ):
            assert raw[field] is None, f"{field} should be None, got {raw[field]!r}"

    def test_constants_always_present_never_exported(self):
        column_map = _column_map()
        raw = importer.row_to_raw_json(_row(), column_map, "MNQU6", "5m")
        assert raw["schema_version"] == "1.0"
        assert raw["source"] == "tradingview"
        assert raw["bar_status"] == "closed"
        assert raw["event_type"] == "bar_closed"
        assert raw["overnight_high_status"] is None
        assert raw["overnight_low_status"] is None
        assert raw["previous_day_high_status"] is None
        assert raw["previous_day_low_status"] is None
        assert raw["liquidity_sweep"] is False
        assert raw["reclaim"] is False
        assert raw["rejection"] is False
        assert raw["displacement"] is False
        assert raw["volume_spike"] is False


class TestValidRowToPayload:
    def test_fully_populated_row_builds_a_valid_payload(self):
        column_map = _column_map()
        raw = importer.row_to_raw_json(
            _row(
                export_rth_open="100.00", export_previous_day_high="105.00", export_previous_day_low="95.00",
                export_overnight_high="103.00", export_overnight_low="97.00", export_vwap="100.25",
                export_distance_from_vwap_points="0.25", export_atr="2.5", export_volume_ratio="1.8",
                export_nearest_liquidity_level="105.00", export_distance_to_liquidity_ticks="18",
                export_is_rth="1", export_trading_date="20260701", export_session_name="1",
                export_nearest_liquidity_type="1", export_trend_1m="1", export_trend_5m="1",
                export_trend_15m="0", export_trend_1h="-1",
            ),
            column_map, "MNQU6", "5m",
        )
        payload = TradingViewMarketStatePayload.model_validate(raw)
        assert payload.symbol == "MNQU6"
        assert payload.session_name == "RTH"
        assert payload.trend_1m == "up"
        assert payload.trend_15m == "flat"
        assert payload.trend_1h == "down"
        assert payload.nearest_liquidity_type == "previous_day_high"
        assert payload.trading_date == "2026-07-01"

    def test_sparse_row_still_builds_a_valid_payload(self):
        column_map = _column_map()
        raw = importer.row_to_raw_json(_row(), column_map, "MNQU6", "5m")
        payload = TradingViewMarketStatePayload.model_validate(raw)
        assert payload.rth_open is None
        assert payload.trend_1m is None


class TestMalformedEnumCode:
    def test_bad_trend_code_raises_before_payload_construction(self):
        column_map = _column_map()
        with pytest.raises(ValueError, match="trend code"):
            importer.row_to_raw_json(_row(export_trend_1m="7"), column_map, "MNQU6", "5m")


class TestMissingRequiredColumn:
    def test_raises_importer_input_error(self):
        with pytest.raises(importer.ImporterInputError, match="required column"):
            importer._build_column_map(["time", "open", "high", "close"], strict=True)

    def test_lenient_mode_does_not_raise(self):
        column_map = importer._build_column_map(["time", "open", "high", "close"], strict=False)
        assert column_map["low"] is None


class TestOneMalformedRowDoesNotAbortValidRows:
    def test_build_candidates_skips_bad_row_keeps_good_ones(self):
        column_map = _column_map()
        rows = [_row(), _row(export_trend_1m="7"), _row(time="2026-07-01T13:05:00Z")]
        candidates, skipped = importer.build_candidates(rows, column_map, "MNQU6", "5m")
        assert len(candidates) == 2
        assert len(skipped) == 1
        assert skipped[0][0] == 3  # row_number, 1-indexed with header offset (row 2 is the bad one)


class TestChronologicalOrdering:
    def test_candidates_sorted_regardless_of_csv_order(self):
        column_map = _column_map()
        rows = [
            _row(time="2026-07-01T13:10:00Z"),
            _row(time="2026-07-01T13:00:00Z"),
            _row(time="2026-07-01T13:05:00Z"),
        ]
        candidates, _skipped = importer.build_candidates(rows, column_map, "MNQU6", "5m")
        timestamps = [c[1] for c in candidates]
        assert timestamps == sorted(timestamps)


class TestDryRunPerformsNoWrites:
    @pytest.mark.asyncio
    async def test_dry_run_never_touches_a_repository(self):
        column_map = _column_map()
        rows = [_row(), _row(time="2026-07-01T13:05:00Z")]
        candidates, _skipped = importer.build_candidates(rows, column_map, "MNQU6", "5m")
        valid, inserted, duplicate, malformed = await importer.process_candidates(
            candidates, repository=None, apply_writes=False,
        )
        assert valid == 2
        assert inserted == 0
        assert duplicate == 0
        assert malformed == []
        # repository=None and apply_writes=False together prove no write path
        # was reachable - a real repository call would have raised
        # AttributeError on None immediately.


class TestCertifiedInvocation:
    """Sprint 31 Task 6 - the exact invocation Task 1/3 certified:
    --symbol MNQ1! --timeframe 5m --assume-bar-open-time [--apply]. No new
    behavior - proves the existing flags already correctly support it."""

    @pytest.mark.asyncio
    async def test_symbol_mnq1_and_bar_open_shift_together(self):
        column_map = _column_map()
        rows = [_row(time="2026-07-20T07:45:00Z"), _row(time="2026-07-20T07:50:00Z")]
        candidates, skipped = importer.build_candidates(rows, column_map, "MNQ1!", "5m", cadence_minutes=5)
        assert skipped == []
        assert len(candidates) == 2
        raw_jsons = [c[2] for c in candidates]
        assert raw_jsons[0]["symbol"] == "MNQ1!"
        assert raw_jsons[0]["timestamp"] == "2026-07-20T07:50:00Z"
        assert raw_jsons[0]["event_id"] == "MNQ1!:5m:2026-07-20T07:50:00Z"
        assert raw_jsons[1]["timestamp"] == "2026-07-20T07:55:00Z"

        repository = InMemoryMarketStateRepository()
        valid, inserted, duplicate, malformed = await importer.process_candidates(candidates, repository, apply_writes=True)
        assert (valid, inserted, duplicate, malformed) == (2, 2, 0, [])


class TestBarOpenShiftAppliedExactlyOnce:
    def test_consecutive_rows_keep_correct_spacing_after_shift(self):
        # Guards against a double-shift or cumulative-drift bug: two rows
        # 5 minutes apart in the CSV (bar-open labels) must still be exactly
        # 5 minutes apart after the shift (bar-close labels), not 10.
        column_map = _column_map()
        rows = [_row(time="2026-07-01T13:00:00Z"), _row(time="2026-07-01T13:05:00Z")]
        candidates, _skipped = importer.build_candidates(rows, column_map, "MNQU6", "5m", cadence_minutes=5)
        occurred_ats = [c[1] for c in candidates]
        assert occurred_ats[0].isoformat() == "2026-07-01T13:05:00+00:00"
        assert occurred_ats[1].isoformat() == "2026-07-01T13:10:00+00:00"
        assert (occurred_ats[1] - occurred_ats[0]).total_seconds() == 300  # exactly 5 minutes, not 10


class TestAnalyticalFloatPrecisionPreservedThroughStorage:
    @pytest.mark.asyncio
    async def test_vwap_survives_the_real_import_and_repository_round_trip(self):
        column_map = _column_map()
        rows = [_row(export_vwap="28849.3104756607")]
        candidates, _skipped = importer.build_candidates(rows, column_map, "MNQU6", "5m")
        repository = InMemoryMarketStateRepository()

        valid, inserted, duplicate, malformed = await importer.process_candidates(candidates, repository, apply_writes=True)
        assert (valid, inserted, duplicate, malformed) == (1, 1, 0, [])

        stored = await repository.get_latest(Symbol("MNQU6"), Timeframe.M5)
        assert stored is not None
        assert stored.vwap == 28849.3104756607  # not tick-rounded, not truncated


class TestMalformedRowReportedClearlyAtApplyStage:
    """Distinct from TestOneMalformedRowDoesNotAbortValidRows above: this is
    a row that parses fine into a raw payload (valid enum codes, valid
    timestamp) but fails Pydantic/translator validation - the
    process_candidates 'malformed' path, not build_candidates' 'skipped'
    path. Untested before this Sprint."""

    @pytest.mark.asyncio
    async def test_off_tick_price_is_reported_not_silently_dropped(self):
        column_map = _column_map()
        rows = [_row(), _row(time="2026-07-01T13:05:00Z", close="100.10")]  # off the 0.25 tick grid
        candidates, _skipped = importer.build_candidates(rows, column_map, "MNQU6", "5m")
        repository = InMemoryMarketStateRepository()

        valid, inserted, duplicate, malformed = await importer.process_candidates(candidates, repository, apply_writes=True)
        assert valid == 1
        assert inserted == 1
        assert len(malformed) == 1
        row_number, reason = malformed[0]
        assert row_number == 3  # header + first good row + this one
        assert "tick grid" in reason

    @pytest.mark.asyncio
    async def test_off_tick_price_reported_in_dry_run_too(self):
        column_map = _column_map()
        rows = [_row(close="100.10")]
        candidates, _skipped = importer.build_candidates(rows, column_map, "MNQU6", "5m")
        valid, inserted, duplicate, malformed = await importer.process_candidates(candidates, repository=None, apply_writes=False)
        assert valid == 0
        assert len(malformed) == 1
        assert "tick grid" in malformed[0][1]


class TestDuplicateRerunBehavior:
    @pytest.mark.asyncio
    async def test_reimporting_the_same_rows_produces_duplicates_not_new_inserts(self):
        column_map = _column_map()
        rows = [_row(), _row(time="2026-07-01T13:05:00Z")]
        candidates, _skipped = importer.build_candidates(rows, column_map, "MNQU6", "5m")
        repository = InMemoryMarketStateRepository()

        first = await importer.process_candidates(candidates, repository, apply_writes=True)
        assert first == (2, 2, 0, [])  # valid, inserted, duplicate, malformed

        second = await importer.process_candidates(candidates, repository, apply_writes=True)
        assert second == (2, 0, 2, [])  # same rows again: all duplicates, zero new inserts

        stored = await repository.get_range(
            Symbol("MNQU6"), Timeframe.M5,
            datetime(2020, 1, 1, tzinfo=timezone.utc), datetime(2030, 1, 1, tzinfo=timezone.utc),
        )
        assert len(stored) == 2  # not 4 - reimporting never doubled the stored rows
