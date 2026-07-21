"""
Sprint RE-1 (expanded dataset). Tests for scripts/run_statistical_profile.py's
multi-CSV merge/dedup/conflict-detection logic - specifically that it
matches MarketStateRepository.ingest()'s real first-insert-wins semantics
for identical-content duplicates, and fails loudly (never silently picks a
version) when the same timestamp carries genuinely different content across
files - since this is what predicts Phase B's actual Inserted/Duplicate
split before ever touching a database.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_statistical_profile.py"
_spec = importlib.util.spec_from_file_location("run_statistical_profile", _SCRIPT_PATH)
runner = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = runner
_spec.loader.exec_module(runner)

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


def _row(epoch, close, vwap="28849.3104756607"):
    return (
        f"{epoch},20120.00,20128.50,20118.00,{close},4210,"
        f"20100.00,20180.00,20050.25,20140.00,20080.50,{vwap},"
        "7.25,42.5,1.35,20180.00,217,1,20260720,1,1,1,1,0,-1\n"
    )


class TestLoadAndMergeStates:
    def test_no_overlap_all_rows_are_new(self, tmp_path):
        csv_a = tmp_path / "a.csv"
        csv_a.write_text(CSV_HEADERS + _row(1784533200, 20125.75) + _row(1784533500, 20126.00), encoding="utf-8")
        csv_b = tmp_path / "b.csv"
        csv_b.write_text(CSV_HEADERS + _row(1784533800, 20126.25), encoding="utf-8")

        states, counts, stats = runner.load_and_merge_states([str(csv_a), str(csv_b)], "MNQ1!", "5m")
        assert len(states) == 3
        assert counts == [(str(csv_a), 2, 2), (str(csv_b), 1, 1)]
        assert stats == {
            "raw_row_count": 3, "unique_row_count": 3,
            "identical_duplicates_removed": 0, "conflict_count": 0,
        }

    def test_identical_content_overlap_is_silently_deduped(self, tmp_path):
        # Exact same row (byte-identical fields) at the same timestamp in
        # both files - the expected, safe case for two adjacent exports'
        # overlap window (Sprint 31/RE-1's own real files behave this way).
        csv_a = tmp_path / "a.csv"
        csv_a.write_text(CSV_HEADERS + _row(1784533200, 111.25), encoding="utf-8")
        csv_b = tmp_path / "b.csv"
        csv_b.write_text(CSV_HEADERS + _row(1784533200, 111.25), encoding="utf-8")

        states, counts, stats = runner.load_and_merge_states([str(csv_a), str(csv_b)], "MNQ1!", "5m")
        assert len(states) == 1
        assert states[0].close.value == 111.25
        assert counts == [(str(csv_a), 1, 1), (str(csv_b), 1, 0)]
        assert stats["identical_duplicates_removed"] == 1
        assert stats["conflict_count"] == 0

    def test_conflicting_content_at_the_same_timestamp_raises_loudly(self, tmp_path):
        # Same timestamp, DIFFERENT close price across files - a genuine
        # conflict. Must never be silently resolved by picking either
        # file's version.
        csv_a = tmp_path / "a.csv"
        csv_a.write_text(CSV_HEADERS + _row(1784533200, 111.25), encoding="utf-8")
        csv_b = tmp_path / "b.csv"
        csv_b.write_text(CSV_HEADERS + _row(1784533200, 999.75), encoding="utf-8")

        with pytest.raises(runner.ConflictingTimestampError, match="1 conflicting timestamp"):
            runner.load_and_merge_states([str(csv_a), str(csv_b)], "MNQ1!", "5m")

    def test_conflicting_vwap_alone_is_also_detected(self, tmp_path):
        # OHLC identical, only the analytical vwap field differs - still a
        # real conflict (the task explicitly names OHLC, VWAP, and Market
        # State values as things to check, not OHLC alone).
        csv_a = tmp_path / "a.csv"
        csv_a.write_text(CSV_HEADERS + _row(1784533200, 111.25, vwap="100.111111"), encoding="utf-8")
        csv_b = tmp_path / "b.csv"
        csv_b.write_text(CSV_HEADERS + _row(1784533200, 111.25, vwap="100.222222"), encoding="utf-8")

        with pytest.raises(runner.ConflictingTimestampError):
            runner.load_and_merge_states([str(csv_a), str(csv_b)], "MNQ1!", "5m")

    def test_dedup_key_matches_repository_unique_constraint_shape(self, tmp_path):
        # event_id is deterministic per (symbol, timeframe, timestamp) - the
        # same key MarketStateRepository.ingest()'s UNIQUE constraint uses.
        csv_a = tmp_path / "a.csv"
        csv_a.write_text(CSV_HEADERS + _row(1784533200, 100.0), encoding="utf-8")
        states, _counts, _stats = runner.load_and_merge_states([str(csv_a)], "MNQ1!", "5m")
        assert states[0].envelope.event_id == "MNQ1!:5m:2026-07-20T07:40:00Z"

    def test_three_files_chronological_merge_with_identical_overlaps(self, tmp_path):
        csv_a = tmp_path / "a.csv"
        csv_a.write_text(CSV_HEADERS + _row(1784533200, 1.0), encoding="utf-8")
        csv_b = tmp_path / "b.csv"
        csv_b.write_text(CSV_HEADERS + _row(1784533200, 1.0) + _row(1784533500, 3.0), encoding="utf-8")
        csv_c = tmp_path / "c.csv"
        csv_c.write_text(CSV_HEADERS + _row(1784533500, 3.0) + _row(1784533800, 5.0), encoding="utf-8")

        states, counts, stats = runner.load_and_merge_states([str(csv_a), str(csv_b), str(csv_c)], "MNQ1!", "5m")
        assert len(states) == 3  # 3 unique timestamps total
        assert counts == [(str(csv_a), 1, 1), (str(csv_b), 2, 1), (str(csv_c), 2, 1)]
        assert stats == {
            "raw_row_count": 5, "unique_row_count": 3,
            "identical_duplicates_removed": 2, "conflict_count": 0,
        }
