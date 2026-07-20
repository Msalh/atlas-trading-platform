"""
Sprint 31 Task 4. Tests for scripts/certify_historical_dataset.py - proves
the certification logic itself is correct (detects a clean dataset,
detects each class of injected defect) using synthetic MarketState fixtures
built directly (not via CSV parsing, which is already covered by
tests/test_import_historical_market_state_csv.py). These tests do not
re-certify the real Sprint 26 CSV - that certification is the report
produced by actually running the script, already included in this
commit's message / the conversation response.
"""
import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "certify_historical_dataset.py"
_spec = importlib.util.spec_from_file_location("certify_historical_dataset", _SCRIPT_PATH)
certifier = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = certifier
_spec.loader.exec_module(certifier)

from atlas.core.events import Event  # noqa: E402
from atlas.core.primitives import Price, Session, Symbol, Timeframe  # noqa: E402
from atlas.market_engine.models import BarStatus, MarketState  # noqa: E402

TICK = 0.25


def _state(seq: int, **overrides) -> MarketState:
    occurred_at = datetime(2026, 7, 13, 13, 0, tzinfo=timezone.utc) + timedelta(minutes=5 * seq)
    base = dict(
        envelope=Event(
            event_type="bar_closed", source="tradingview", occurred_at=occurred_at,
            received_at=occurred_at, event_id=f"e-{seq}",
        ),
        schema_version="1.0", symbol=Symbol("MNQ1!"), timeframe=Timeframe.M5, bar_status=BarStatus.CLOSED,
        open=Price(20120.00, TICK), high=Price(20128.50, TICK), low=Price(20118.00, TICK), close=Price(20125.75, TICK),
        volume=4210, session_name=Session.RTH, is_rth=True, trading_date=occurred_at.date(),
        rth_open=Price(19980.00, TICK),
        previous_day_high=Price(20180.00, TICK), previous_day_low=Price(19950.00, TICK),
        overnight_high=Price(20300.00, TICK), overnight_low=Price(19900.00, TICK),
        vwap=28849.3104756607, distance_from_vwap_points=20125.75 - 28849.3104756607,
        atr=42.5, volume_ratio=1.35,
        nearest_liquidity_level=Price(20180.00, TICK), nearest_liquidity_type="previous_day_high",
        distance_to_liquidity_ticks=217,
        trend_1m="up", trend_5m="up", trend_15m="flat", trend_1h="down",
        liquidity_sweep=False, reclaim=False, rejection=False, displacement=False, volume_spike=False,
    )
    base.update(overrides)
    return MarketState(**base)


def _clean_series(n=5):
    return [_state(i) for i in range(n)]


class TestDatasetIdentity:
    def test_consistent_symbol_and_timeframe_pass(self):
        results = certifier.check_dataset_identity(_clean_series(), "MNQ1!", "5m")
        by_check = {r.check: r for r in results}
        assert by_check["Symbol consistency"].verdict == certifier.PASS
        assert by_check["Timeframe consistency"].verdict == certifier.PASS

    def test_symbol_provenance_is_always_a_warning(self):
        results = certifier.check_dataset_identity(_clean_series(), "MNQ1!", "5m")
        by_check = {r.check: r for r in results}
        assert by_check["Symbol provenance"].verdict == certifier.WARNING

    def test_mismatched_symbol_fails(self):
        states = [_state(0, symbol=Symbol("SOMETHING_ELSE"))]
        results = certifier.check_dataset_identity(states, "MNQ1!", "5m")
        by_check = {r.check: r for r in results}
        assert by_check["Symbol consistency"].verdict == certifier.FAIL

    def test_empty_dataset_fails(self):
        results = certifier.check_dataset_identity([], "MNQ1!", "5m")
        assert results[0].verdict == certifier.FAIL


class TestTimeContinuity:
    def test_clean_series_passes(self):
        results = certifier.check_time_continuity(_clean_series(), Timeframe.M5)
        by_check = {r.check: r for r in results}
        assert by_check["Duplicate timestamps"].verdict == certifier.PASS
        assert by_check["Chronological ordering"].verdict == certifier.PASS
        assert by_check["Gap detection"].verdict == certifier.PASS

    def test_duplicate_timestamp_fails(self):
        base = _clean_series(3)
        duplicate = _state(1, envelope=base[1].envelope)  # same occurred_at as index 1
        results = certifier.check_time_continuity(base + [duplicate], Timeframe.M5)
        by_check = {r.check: r for r in results}
        assert by_check["Duplicate timestamps"].verdict == certifier.FAIL

    def test_real_gap_is_a_warning_not_a_fail(self):
        states = [_state(0), _state(50)]  # a large jump, no duplicates/reversals
        results = certifier.check_time_continuity(states, Timeframe.M5)
        by_check = {r.check: r for r in results}
        assert by_check["Gap detection"].verdict == certifier.WARNING
        assert by_check["Duplicate timestamps"].verdict == certifier.PASS


class TestSessionIntegrity:
    def test_clean_series_passes(self):
        results = certifier.check_session_integrity(_clean_series())
        assert all(r.verdict == certifier.PASS for r in results)

    def test_is_rth_session_name_mismatch_fails(self):
        states = [_state(0, is_rth=True, session_name=Session.OVERNIGHT)]
        results = certifier.check_session_integrity(states)
        by_check = {r.check: r for r in results}
        assert by_check["is_rth / session_name consistency"].verdict == certifier.FAIL

    def test_overnight_level_changing_mid_rth_fails(self):
        states = [
            _state(0, overnight_high=Price(20140.00, TICK)),
            _state(1, overnight_high=Price(20160.00, TICK)),  # changed while still RTH
        ]
        results = certifier.check_session_integrity(states)
        by_check = {r.check: r for r in results}
        assert by_check["Overnight reset-and-hold invariant"].verdict == certifier.FAIL

    def test_trading_date_going_backwards_fails(self):
        states = [
            _state(0, trading_date=datetime(2026, 7, 14).date()),
            _state(1, trading_date=datetime(2026, 7, 13).date()),
        ]
        results = certifier.check_session_integrity(states)
        by_check = {r.check: r for r in results}
        assert by_check["trading_date monotonicity"].verdict == certifier.FAIL


class TestMarketDataIntegrity:
    def test_clean_series_passes(self):
        results = certifier.check_market_data_integrity(_clean_series())
        assert all(r.verdict == certifier.PASS for r in results)

    def test_high_below_close_fails_ohlc_check(self):
        states = [_state(0, high=Price(20120.00, TICK), close=Price(20125.75, TICK))]
        results = certifier.check_market_data_integrity(states)
        by_check = {r.check: r for r in results}
        assert by_check["OHLC consistency"].verdict == certifier.FAIL

    def test_negative_volume_fails(self):
        states = [_state(0, volume=-1)]
        results = certifier.check_market_data_integrity(states)
        by_check = {r.check: r for r in results}
        assert by_check["Volume validity"].verdict == certifier.FAIL

    def test_null_vwap_fails(self):
        states = [_state(0, vwap=None)]
        results = certifier.check_market_data_integrity(states)
        by_check = {r.check: r for r in results}
        assert by_check["VWAP validity"].verdict == certifier.FAIL

    def test_a_few_null_atr_at_series_start_is_a_warning_not_a_fail(self):
        states = [_state(0, atr=None), _state(1, atr=None)] + _clean_series(3)
        results = certifier.check_market_data_integrity(states)
        by_check = {r.check: r for r in results}
        assert by_check["ATR validity"].verdict == certifier.WARNING

    def test_pervasive_null_atr_fails(self):
        states = [_state(i, atr=None) for i in range(25)]
        results = certifier.check_market_data_integrity(states)
        by_check = {r.check: r for r in results}
        assert by_check["ATR validity"].verdict == certifier.FAIL


class TestFeatureIntegrity:
    def test_clean_series_passes(self):
        results = certifier.check_feature_integrity(_clean_series())
        by_check = {r.check: r for r in results}
        assert by_check["distance_from_vwap_points consistency"].verdict == certifier.PASS
        assert by_check["nearest_liquidity_level/type consistency"].verdict == certifier.PASS

    def test_placeholder_flags_all_false_is_a_warning_by_design(self):
        results = certifier.check_feature_integrity(_clean_series())
        by_check = {r.check: r for r in results}
        assert by_check["Rule Engine placeholder flags"].verdict == certifier.WARNING

    def test_unexpected_non_false_placeholder_flag_fails(self):
        states = [_state(0, reclaim=True)]
        results = certifier.check_feature_integrity(states)
        by_check = {r.check: r for r in results}
        assert by_check["Rule Engine placeholder flags"].verdict == certifier.FAIL

    def test_distance_from_vwap_mismatch_fails(self):
        states = [_state(0, distance_from_vwap_points=999.0)]
        results = certifier.check_feature_integrity(states)
        by_check = {r.check: r for r in results}
        assert by_check["distance_from_vwap_points consistency"].verdict == certifier.FAIL

    def test_nearest_liquidity_level_not_matching_its_claimed_type_fails(self):
        states = [_state(0, nearest_liquidity_type="overnight_low")]  # level is still previous_day_high's value
        results = certifier.check_feature_integrity(states)
        by_check = {r.check: r for r in results}
        assert by_check["nearest_liquidity_level/type consistency"].verdict == certifier.FAIL

    def test_invalid_trend_value_fails(self):
        states = [_state(0, trend_1m="sideways")]
        results = certifier.check_feature_integrity(states)
        by_check = {r.check: r for r in results}
        assert by_check["trend_1m validity"].verdict == certifier.FAIL


class TestRenderReport:
    def test_no_fails_no_warnings_is_certified(self):
        results = certifier.check_market_data_integrity(_clean_series())
        report = certifier.render_report(results)
        assert "VERDICT: CERTIFIED" in report
        assert "REJECTED" not in report

    def test_any_fail_is_rejected(self):
        results = certifier.check_market_data_integrity([_state(0, volume=-1)])
        report = certifier.render_report(results)
        assert "VERDICT: REJECTED" in report

    def test_warning_without_fail_is_certified_with_warnings(self):
        results = certifier.check_time_continuity([_state(0), _state(50)], Timeframe.M5)
        report = certifier.render_report(results)
        assert "VERDICT: CERTIFIED WITH WARNINGS" in report
