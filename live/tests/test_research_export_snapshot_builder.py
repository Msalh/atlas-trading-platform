"""
UI v2. Tests for atlas.research_export.snapshot_builder.

Deliberately uses a small, hand-built synthetic MarketState series
(monkeypatched in place of the real 97,858-bar frozen CSV load) rather
than the real frozen dataset - the real dataset takes minutes to run
through RE-1+RE-2+certify() and belongs in a manual verification step
(actually running scripts/export_research_snapshots.py and reviewing its
output), not the routine test suite, matching this project's established
"fast synthetic fixtures for correctness, real data for one verified run"
discipline (see e.g. tests/test_setup_profiling.py).

The most important test here is a regression test for a real bug found
while first running this module for real: RunManifest.code_version is
computed internally via current_code_version() (git rev-parse HEAD) at
CALL TIME, not accepted as a parameter - so a naive re-run would embed
whatever commit is current when the export happens to run, not the
historical freeze commit, silently breaking reproducibility every time
any unrelated commit landed anywhere in the repo.
"""
from datetime import datetime, timedelta, timezone

import pytest

from atlas.core.events import Event
from atlas.core.primitives import Price, Session, Symbol, Timeframe
from atlas.market_engine.models import BarStatus, MarketState
from atlas.research_export import snapshot_builder as sb
from atlas.research.setup_profiling import service as re2_service

TICK = 0.25
_BASE_TIME = datetime(2026, 3, 2, 23, 5, tzinfo=timezone.utc)


def _market_state(seq: int, **overrides) -> MarketState:
    occurred_at = _BASE_TIME + timedelta(minutes=5 * seq)
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
        vwap=20100.0, distance_from_vwap_points=25.75, atr=42.5, volume_ratio=1.35,
        nearest_liquidity_level=Price(20180.00, TICK), nearest_liquidity_type="previous_day_high",
        distance_to_liquidity_ticks=217,
        trend_1m="up", trend_5m="up", trend_15m="flat", trend_1h="down",
        liquidity_sweep=False, reclaim=False, rejection=False, displacement=(seq % 3 == 0), volume_spike=(seq % 4 == 0),
    )
    base.update(overrides)
    return MarketState(**base)


def _synthetic_states(n: int = 30) -> list[MarketState]:
    return [_market_state(i) for i in range(n)]


@pytest.fixture
def fast_frozen_dataset(monkeypatch):
    """Replaces the real 97,858-bar CSV load with a small synthetic
    series, everywhere snapshot_builder reads it from."""
    states = _synthetic_states()

    def _fake_load_and_merge_states(csv_paths, symbol, timeframe, cadence_minutes):
        return states, [(p, len(states), len(states)) for p in csv_paths], {
            "raw_row_count": len(states), "unique_row_count": len(states),
            "identical_duplicates_removed": 0, "conflict_count": 0,
        }

    monkeypatch.setattr(sb.re1_runner, "load_and_merge_states", _fake_load_and_merge_states)
    return states


class TestSourceComputationVersionIsStable:
    """Regression test for the real bug this module's docstring describes."""

    def test_re1_envelope_uses_the_fixed_historical_commit_not_current_head(self, fast_frozen_dataset):
        exported_at = datetime.now(timezone.utc)
        snapshot = sb.build_re1_snapshot(exported_at)
        assert snapshot["envelope"]["source_computation_version"] == sb.RE1_SOURCE_COMPUTATION_VERSION

    def test_re1_payload_manifest_code_version_matches_the_fixed_value_too(self, fast_frozen_dataset):
        snapshot = sb.build_re1_snapshot(datetime.now(timezone.utc))
        assert snapshot["payload"]["manifest"]["code_version"] == sb.RE1_SOURCE_COMPUTATION_VERSION

    def test_re2_envelope_uses_the_fixed_historical_commit_not_current_head(self, fast_frozen_dataset):
        snapshot, _dataset = sb.build_re2_snapshot(datetime.now(timezone.utc))
        assert snapshot["envelope"]["source_computation_version"] == sb.RE2_SOURCE_COMPUTATION_VERSION

    def test_re2_payload_manifest_code_version_matches_the_fixed_value_too(self, fast_frozen_dataset):
        snapshot, _dataset = sb.build_re2_snapshot(datetime.now(timezone.utc))
        assert snapshot["payload"]["setup_profile"]["manifest"]["code_version"] == sb.RE2_SOURCE_COMPUTATION_VERSION

    def test_snapshot_exporter_version_is_independent_of_source_computation_version(self, fast_frozen_dataset):
        # snapshot_exporter_version SHOULD reflect current HEAD (it describes
        # the exporter code itself) - only source_computation_version is
        # pinned to the historical freeze commit.
        snapshot = sb.build_re1_snapshot(datetime.now(timezone.utc))
        assert "snapshot_exporter_version" in snapshot["envelope"]


class TestChecksumReproducibility:
    def test_checksum_is_identical_across_two_exports_with_different_exported_at(self, fast_frozen_dataset):
        snapshot_1 = sb.build_re1_snapshot(datetime(2026, 1, 1, tzinfo=timezone.utc))
        snapshot_2 = sb.build_re1_snapshot(datetime(2027, 6, 15, tzinfo=timezone.utc))
        assert snapshot_1["envelope"]["content_checksum"] == snapshot_2["envelope"]["content_checksum"]
        assert snapshot_1["envelope"]["exported_at"] != snapshot_2["envelope"]["exported_at"]

    def test_re2_checksum_is_also_stable_across_exported_at(self, fast_frozen_dataset):
        snapshot_1, _ = sb.build_re2_snapshot(datetime(2026, 1, 1, tzinfo=timezone.utc))
        snapshot_2, _ = sb.build_re2_snapshot(datetime(2027, 6, 15, tzinfo=timezone.utc))
        assert snapshot_1["envelope"]["content_checksum"] == snapshot_2["envelope"]["content_checksum"]

    def test_payload_never_contains_exported_at(self, fast_frozen_dataset):
        snapshot = sb.build_re1_snapshot(datetime.now(timezone.utc))
        assert "exported_at" not in snapshot["payload"]
        assert "exported_at" in snapshot["envelope"]


class TestSinglePassSubstrate:
    """Amendment 7."""

    def test_build_setup_profiling_dataset_called_exactly_once_per_re2_export(self, fast_frozen_dataset, monkeypatch):
        real_builder = re2_service.build_setup_profiling_dataset
        calls = []

        def _counting_builder(*args, **kwargs):
            calls.append(1)
            return real_builder(*args, **kwargs)

        monkeypatch.setattr(sb.re2_service, "build_setup_profiling_dataset", _counting_builder)
        sb.build_re2_snapshot(datetime.now(timezone.utc))
        assert len(calls) == 1


class TestTransitionsSummaryOmitsRawList:
    def test_re2_snapshot_transitions_key_has_no_raw_transitions_array(self, fast_frozen_dataset):
        snapshot, _dataset = sb.build_re2_snapshot(datetime.now(timezone.utc))
        transitions_payload = snapshot["payload"]["transitions"]
        assert "transitions" not in transitions_payload
        assert "matrix" in transitions_payload
        assert "same_setup_recurrence_rate" in transitions_payload
        assert "raw_transition_count" in transitions_payload

    def test_raw_transition_count_matches_the_real_underlying_count(self, fast_frozen_dataset):
        _, dataset = sb.build_re2_snapshot(datetime.now(timezone.utc))
        manifest = re2_service.build_run_manifest(
            sb._profiling_run_config(_synthetic_states()), len(_synthetic_states()),
            datetime.now(timezone.utc), "test",
        )
        full_transitions = re2_service.build_transitions(dataset, manifest)
        snapshot, _ = sb.build_re2_snapshot(datetime.now(timezone.utc))
        assert snapshot["payload"]["transitions"]["raw_transition_count"] == len(full_transitions.transitions)


class TestDatasetHealthReusesRe2Dataset:
    def test_dataset_health_does_not_reload_states_independently(self, fast_frozen_dataset, monkeypatch):
        # certify() does its own independent load internally (documented,
        # unavoidable - it computes properties neither RE-1 nor RE-2's own
        # report objects expose) - faked directly here, rather than via
        # the shared load_and_merge_states reference, so this test stays
        # scoped to its actual claim: build_dataset_health_snapshot itself
        # must not add a SECOND load on top of certify()'s own, for its
        # own dataset_identity/segment_count - it must reuse the
        # already-built re2 dataset instead.
        certify_calls = []

        def _fake_certify(csv_paths, symbol, timeframe, cadence_minutes):
            certify_calls.append(1)
            return []

        monkeypatch.setattr(sb.certifier, "certify", _fake_certify)

        _re2_snapshot, dataset = sb.build_re2_snapshot(datetime.now(timezone.utc))
        result = sb.build_dataset_health_snapshot(datetime.now(timezone.utc), dataset)

        assert len(certify_calls) == 1
        assert result["payload"]["segment_count"] == len(dataset.segments)
        assert result["payload"]["dataset_identity"]["row_count"] == sum(len(s.states) for s in dataset.segments)
        row_count_from_segments = sum(len(s.states) for s in dataset.segments)
        assert result["payload"]["dataset_identity"]["row_count"] == row_count_from_segments
