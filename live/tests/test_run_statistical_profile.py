"""
Sprint RE-1 (expanded dataset). Tests for scripts/run_statistical_profile.py's
multi-CSV merge/dedup logic - specifically that it matches
MarketStateRepository.ingest()'s real first-insert-wins semantics exactly,
since this is what predicts Phase B's actual Inserted/Duplicate counts
before ever touching a database.
"""
import importlib.util
import sys
from pathlib import Path

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


def _row(epoch, close):
    return (
        f"{epoch},20120.00,20128.50,20118.00,{close},4210,"
        "20100.00,20180.00,20050.25,20140.00,20080.50,28849.3104756607,"
        "7.25,42.5,1.35,20180.00,217,1,20260720,1,1,1,1,0,-1\n"
    )


class TestLoadAndMergeStates:
    def test_no_overlap_all_rows_are_new(self, tmp_path):
        csv_a = tmp_path / "a.csv"
        csv_a.write_text(CSV_HEADERS + _row(1784533200, 20125.75) + _row(1784533500, 20126.00), encoding="utf-8")
        csv_b = tmp_path / "b.csv"
        csv_b.write_text(CSV_HEADERS + _row(1784533800, 20126.25), encoding="utf-8")

        states, counts = runner.load_and_merge_states([str(csv_a), str(csv_b)], "MNQ1!", "5m")
        assert len(states) == 3
        assert counts == [(str(csv_a), 2, 2), (str(csv_b), 1, 1)]

    def test_overlap_keeps_the_first_files_version(self, tmp_path):
        # Same timestamp in both files, DIFFERENT close price - proves the
        # first file's row wins, matching real UNIQUE-constraint dedup
        # (the second insert is a no-op, never an overwrite).
        csv_a = tmp_path / "a.csv"
        csv_a.write_text(CSV_HEADERS + _row(1784533200, 111.25), encoding="utf-8")
        csv_b = tmp_path / "b.csv"
        csv_b.write_text(CSV_HEADERS + _row(1784533200, 999.75), encoding="utf-8")

        states, counts = runner.load_and_merge_states([str(csv_a), str(csv_b)], "MNQ1!", "5m")
        assert len(states) == 1
        assert states[0].close.value == 111.25  # file a's version, not file b's
        assert counts == [(str(csv_a), 1, 1), (str(csv_b), 1, 0)]  # b contributed zero NEW rows

    def test_dedup_key_matches_repository_unique_constraint_shape(self, tmp_path):
        # event_id is deterministic per (symbol, timeframe, timestamp) - the
        # same key MarketStateRepository.ingest()'s UNIQUE constraint uses.
        csv_a = tmp_path / "a.csv"
        csv_a.write_text(CSV_HEADERS + _row(1784533200, 100.0), encoding="utf-8")
        states, _counts = runner.load_and_merge_states([str(csv_a)], "MNQ1!", "5m")
        assert states[0].envelope.event_id == "MNQ1!:5m:2026-07-20T07:40:00Z"

    def test_three_files_chronological_first_wins_order_preserved(self, tmp_path):
        csv_a = tmp_path / "a.csv"
        csv_a.write_text(CSV_HEADERS + _row(1784533200, 1.0), encoding="utf-8")
        csv_b = tmp_path / "b.csv"
        csv_b.write_text(CSV_HEADERS + _row(1784533200, 2.0) + _row(1784533500, 3.0), encoding="utf-8")
        csv_c = tmp_path / "c.csv"
        csv_c.write_text(CSV_HEADERS + _row(1784533500, 4.0) + _row(1784533800, 5.0), encoding="utf-8")

        states, counts = runner.load_and_merge_states([str(csv_a), str(csv_b), str(csv_c)], "MNQ1!", "5m")
        assert len(states) == 3  # 3 unique timestamps total
        assert counts == [(str(csv_a), 1, 1), (str(csv_b), 2, 1), (str(csv_c), 2, 1)]
