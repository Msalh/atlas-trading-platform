"""
Sprint 31 Task 3. Tests for scripts/verify_historical_live_equivalence.py -
the Historical vs Live Equivalence certification utility. Imports the script
as a module directly, matching the existing pattern
tests/test_import_historical_market_state_csv.py already uses for scripts
under scripts/.

These tests prove the comparison TOOL is correct (detects a real match,
detects an introduced mismatch, reads real files correctly) using synthetic,
controlled fixture data - they do not and cannot certify Sprint 31 Task 3
itself. That certification requires the actual fresh historical CSV and the
actual saved production /export responses for the three real timestamps,
neither of which exists in this repository or this session.
"""
import importlib.util
import json
import sys
from pathlib import Path

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "verify_historical_live_equivalence.py"
_spec = importlib.util.spec_from_file_location("verify_historical_live_equivalence", _SCRIPT_PATH)
verifier = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = verifier
_spec.loader.exec_module(verifier)


def _full_state(**overrides):
    state = {
        "open": 20120.00, "high": 20128.50, "low": 20118.00, "close": 20125.75,
        "vwap": 28849.3104756607, "atr": 42.5, "volume": 4210, "volume_ratio": 1.35,
        "distance_from_vwap_points": 7.25,
        "nearest_liquidity_level": 20180.00, "nearest_liquidity_type": "previous_day_high",
        "trend_1m": "up", "trend_5m": "up", "trend_15m": "flat", "trend_1h": "down",
        "liquidity_sweep": False, "reclaim": False, "rejection": False,
        "displacement": False, "volume_spike": False,
    }
    state.update(overrides)
    return state


CSV_HEADERS = (
    "time,open,high,low,close,volume,"
    "export_rth_open,export_previous_day_high,export_previous_day_low,"
    "export_overnight_high,export_overnight_low,export_vwap,"
    "export_distance_from_vwap_points,export_atr,export_volume_ratio,"
    "export_nearest_liquidity_level,export_distance_to_liquidity_ticks,"
    "export_is_rth,export_trading_date,export_session_name,"
    "export_nearest_liquidity_type,export_trend_1m,export_trend_5m,"
    "export_trend_15m,export_trend_1h\n"
)


def _csv_row(time="2026-07-20T07:50:00Z", vwap=28849.3104756607):
    # nearest_liquidity_type=1 -> "previous_day_high", trend codes 1/1/0/-1 ->
    # up/up/flat/down (importer's own _TREND_DECODE/_LIQUIDITY_TYPE_DECODE),
    # trading_date=20260720, session_name=1 -> RTH, is_rth=1.
    return (
        f"{time},20120.00,20128.50,20118.00,20125.75,4210,"
        "20100.00,20180.00,20050.25,20140.00,20080.50,28849.3104756607,"
        "7.25,42.5,1.35,20180.00,217,1,20260720,1,1,1,1,0,-1\n"
    )


class TestCompareFields:
    def test_identical_states_all_pass(self):
        results = verifier.compare_fields(_full_state(), _full_state())
        assert all(r.passed for r in results)
        assert len(results) == 20  # exact field count specified for this certification

    def test_single_mismatch_is_reported_and_fails_only_that_field(self):
        historical = _full_state()
        live = _full_state(vwap=28849.9999999999)
        results = {r.field: r for r in verifier.compare_fields(historical, live)}
        assert results["vwap"].passed is False
        assert results["open"].passed is True
        assert results["close"].passed is True

    def test_no_tolerance_a_tiny_float_difference_still_fails(self):
        # Sprint 29A.6's own standard for this proof: "not approximately,
        # exactly" - a benign-looking last-digit difference must still FAIL,
        # never be silently rounded away.
        historical = _full_state(atr=42.500000001)
        live = _full_state(atr=42.5)
        results = {r.field: r for r in verifier.compare_fields(historical, live)}
        assert results["atr"].passed is False

    def test_trivially_constant_fields_are_flagged(self):
        results = {r.field: r for r in verifier.compare_fields(_full_state(), _full_state())}
        for field in ("liquidity_sweep", "reclaim", "rejection", "displacement", "volume_spike"):
            assert results[field].trivially_constant is True
        assert results["vwap"].trivially_constant is False

    def test_all_twenty_required_fields_are_covered(self):
        expected = {
            "open", "high", "low", "close", "vwap", "atr", "volume", "volume_ratio",
            "distance_from_vwap_points", "nearest_liquidity_level", "nearest_liquidity_type",
            "trend_1m", "trend_5m", "trend_15m", "trend_1h",
            "liquidity_sweep", "reclaim", "rejection", "displacement", "volume_spike",
        }
        results = verifier.compare_fields(_full_state(), _full_state())
        assert {r.field for r in results} == expected


class TestRenderReport:
    def test_all_pass_concludes_pass(self):
        results = verifier.compare_fields(_full_state(), _full_state())
        report = verifier.render_report({"2026-07-20T07:50:00Z": results})
        assert "Task 3 - Historical <-> Live Equivalence: PASS" in report

    def test_any_mismatch_concludes_fail(self):
        results = verifier.compare_fields(_full_state(), _full_state(close=20125.80))
        report = verifier.render_report({"2026-07-20T07:50:00Z": results})
        assert "Task 3 - Historical <-> Live Equivalence: FAIL" in report
        assert "Task 3 - Historical <-> Live Equivalence: PASS" not in report

    def test_report_notes_the_trivially_constant_fields(self):
        results = verifier.compare_fields(_full_state(), _full_state())
        report = verifier.render_report({"2026-07-20T07:50:00Z": results})
        assert "hardcoded false on both the live and historical Pine paths" in report


class TestHistoricalStateAt:
    def test_finds_and_translates_the_matching_row(self, tmp_path):
        csv_path = tmp_path / "export.csv"
        csv_path.write_text(CSV_HEADERS + _csv_row(), encoding="utf-8")
        state = verifier.historical_state_at(str(csv_path), "MNQ1!", "5m", "2026-07-20T07:50:00Z")
        assert state is not None
        assert state["close"] == 20125.75
        assert state["vwap"] == 28849.3104756607

    def test_returns_none_when_timestamp_not_present(self, tmp_path):
        csv_path = tmp_path / "export.csv"
        csv_path.write_text(CSV_HEADERS + _csv_row(time="2026-07-20T07:50:00Z"), encoding="utf-8")
        state = verifier.historical_state_at(str(csv_path), "MNQ1!", "5m", "2026-07-20T08:00:00Z")
        assert state is None

    def test_without_cadence_shift_a_bar_open_labeled_row_is_found_at_its_own_timestamp(self, tmp_path):
        # A CSV row labeled with its bar-OPEN time (TradingView's native chart
        # -export convention, confirmed by Sprint 31 Task 3's real evidence)
        # matches directly at that same timestamp when no shift is applied.
        csv_path = tmp_path / "export.csv"
        csv_path.write_text(CSV_HEADERS + _csv_row(time="2026-07-20T07:45:00Z"), encoding="utf-8")
        assert verifier.historical_state_at(str(csv_path), "MNQ1!", "5m", "2026-07-20T07:45:00Z") is not None
        assert verifier.historical_state_at(str(csv_path), "MNQ1!", "5m", "2026-07-20T07:50:00Z") is None

    def test_cadence_shift_matches_the_bar_close_timestamp_instead(self, tmp_path):
        # Reuses import_historical_market_state_csv.py's own --assume-bar-
        # open-time mechanism (cadence_minutes) unchanged - not a second
        # implementation. A row natively labeled 07:45 (bar-open) shifts to
        # 07:50 (bar-close) and is found there instead, matching the live
        # webhook's own time_close convention.
        csv_path = tmp_path / "export.csv"
        csv_path.write_text(CSV_HEADERS + _csv_row(time="2026-07-20T07:45:00Z"), encoding="utf-8")
        assert verifier.historical_state_at(str(csv_path), "MNQ1!", "5m", "2026-07-20T07:45:00Z", cadence_minutes=5) is None
        shifted = verifier.historical_state_at(str(csv_path), "MNQ1!", "5m", "2026-07-20T07:50:00Z", cadence_minutes=5)
        assert shifted is not None
        assert shifted["close"] == 20125.75


class TestLiveStateFromExportResponse:
    def test_reads_the_single_event(self, tmp_path):
        response_path = tmp_path / "export_response.json"
        response_path.write_text(json.dumps({
            "ok": True, "symbol": "MNQ1!", "timeframe": "5m", "count": 1, "gap_count": 0,
            "gaps": [], "data": [_full_state()],
        }), encoding="utf-8")
        state = verifier.live_state_from_export_response(str(response_path))
        assert state["close"] == 20125.75

    def test_rejects_a_response_with_more_than_one_event(self, tmp_path):
        # Exactly the moving-target failure mode Task 3 already identified -
        # this tool must refuse to silently compare against the wrong event
        # rather than picking one arbitrarily.
        response_path = tmp_path / "export_response.json"
        response_path.write_text(json.dumps({
            "ok": True, "data": [_full_state(), _full_state(close=20130.00)],
        }), encoding="utf-8")
        try:
            verifier.live_state_from_export_response(str(response_path))
            assert False, "expected ValueError"
        except ValueError as e:
            assert "expected exactly 1" in str(e)

    def test_rejects_a_response_with_zero_events(self, tmp_path):
        response_path = tmp_path / "export_response.json"
        response_path.write_text(json.dumps({"ok": True, "data": []}), encoding="utf-8")
        try:
            verifier.live_state_from_export_response(str(response_path))
            assert False, "expected ValueError"
        except ValueError as e:
            assert "expected exactly 1" in str(e)
