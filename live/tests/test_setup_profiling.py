"""
Sprint RE-2. Focused unit tests for atlas.research.setup_profiling.service -
episode construction (activation/continuation/termination/censoring), gap
and segment boundaries, non-computable boundaries, overlap (the interval
sweep and its containment logic), clustering (within-segment gaps and
censored_by_gap), and transition censoring.

Test data is hand-built (synthetic MarketState/RuleEngineOutput/
SetupEngineOutput with explicit, known FactOutcome/SetupOutcome values) so
every expected episode/overlap/gap/transition is computed by hand and
asserted exactly - this exercises this package's OWN new code (the episode
walk, the interval sweep, clustering, transition censoring), not Rule/Setup
Engine's own already-tested evaluation logic.
"""
from datetime import datetime, timedelta, timezone

from atlas.core.events import Event
from atlas.core.primitives import Price, Session, Symbol, Timeframe
from atlas.market_engine.models import BarStatus, MarketState
from atlas.research.setup_profiling import service
from atlas.research.setup_profiling.models import RegisteredFactSnapshot, SetupEpisode, TerminationReason
from atlas.rule_engine.models import FactResult, RuleEngineOutput
from atlas.rule_engine.models import InsufficientData as FactInsufficientData
from atlas.setup_engine.models import SetupEngineOutput, SetupEvidence, SetupResult, Severity
from atlas.setup_engine.models import InsufficientData as SetupInsufficientData

TICK = 0.25
_BASE_TIME = datetime(2026, 7, 13, 13, 0, tzinfo=timezone.utc)

_DEFAULT_FACT_VALUES = {
    "volume_spike": False, "displacement": False, "rejection": False,
    "trend_5m": "flat", "liquidity_sweep": False, "reclaim": False, "vwap_relationship": "within_band",
}


def _iso(seq: int) -> str:
    return (_BASE_TIME + timedelta(minutes=5 * seq)).isoformat()


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
        liquidity_sweep=False, reclaim=False, rejection=False, displacement=False, volume_spike=False,
    )
    base.update(overrides)
    return MarketState(**base)


def _rule_output(seq: int, insufficient: tuple = ()) -> RuleEngineOutput:
    facts = {}
    for name, default in _DEFAULT_FACT_VALUES.items():
        if name in insufficient:
            facts[name] = FactInsufficientData(fact_name=name, definition_version="test", reason="test-insufficient")
        else:
            facts[name] = FactResult(fact_name=name, definition_version="test", value=default, evidence={})
    return RuleEngineOutput(schema_version="1.0", symbol="MNQ1!", timeframe="5m", occurred_at=_iso(seq), facts=facts)


def _setup_outcome(setup_name: str, computable: bool, detected: bool = False):
    if not computable:
        return SetupInsufficientData(setup_name=setup_name, definition_version="test", reason="test-insufficient")
    return SetupResult(
        setup_name=setup_name, definition_version="test", detected=detected,
        severity=(Severity.NORMAL if detected else None), evidence=SetupEvidence(supporting_facts=()),
    )


def _setup_output(seq: int, outcomes: dict) -> SetupEngineOutput:
    return SetupEngineOutput(
        schema_version="1.0", symbol="MNQ1!", timeframe="5m", occurred_at=_iso(seq),
        setups=tuple(outcomes.values()),
    )


def _build_segment(setup_name: str, sequence: list, is_last: bool, start_seq: int = 0) -> "service._Segment":
    """`sequence` is a list of True/False/None per bar position (None =
    InsufficientData for this setup at that bar). `start_seq` offsets every
    bar's timestamp so two independently-built segments (e.g. to prove
    episodes never bridge between them) land in genuinely different,
    non-overlapping time ranges - segment_id is derived from the first
    bar's own timestamp."""
    n = len(sequence)
    seqs = list(range(start_seq, start_seq + n))
    states = [_market_state(i) for i in seqs]
    rule_outputs = [_rule_output(i) for i in seqs]
    setup_outputs = []
    for i, det in zip(seqs, sequence):
        computable = det is not None
        outcome = _setup_outcome(setup_name, computable, detected=bool(det) if computable else False)
        setup_outputs.append(_setup_output(i, {setup_name: outcome}))
    return service._Segment(states, rule_outputs, setup_outputs, is_last=is_last)


def _fact_snapshot(**overrides) -> RegisteredFactSnapshot:
    base = dict(
        volume_spike=False, displacement=False, rejection=False, trend_5m="flat",
        liquidity_sweep=False, reclaim=False, vwap_relationship="within_band",
    )
    base.update(overrides)
    return RegisteredFactSnapshot(**base)


def _episode(
    setup_name: str, segment_id: str, start_seq: int, end_seq: int,
    term: TerminationReason = TerminationReason.BECAME_FALSE, left: bool = False, right: bool = False,
    session: str = "RTH", trading_date: str = "2026-07-13",
) -> SetupEpisode:
    return SetupEpisode(
        setup_name=setup_name, segment_id=segment_id,
        start_timestamp=_iso(start_seq), end_timestamp=_iso(end_seq), duration_bars=end_seq - start_seq + 1,
        start_state=_fact_snapshot(), end_state=_fact_snapshot(),
        session=session, hour_ct="13:00", weekday_ct="Monday", trading_date=trading_date,
        termination_reason=term, is_left_censored=left, is_right_censored=right,
    )


# ---------------------------------------------------------------------------
# Episode construction / termination / censoring
# ---------------------------------------------------------------------------

class TestEpisodeConstruction:
    def test_simple_activation_then_became_false(self):
        segment = _build_segment("s", [False, True, True, False], is_last=False)
        episodes, _records = service._walk_setup_in_segment("s", segment)
        assert len(episodes) == 1
        ep = episodes[0]
        assert ep.start_timestamp == _iso(1) and ep.end_timestamp == _iso(2)
        assert ep.duration_bars == 2
        assert ep.termination_reason == TerminationReason.BECAME_FALSE
        assert not ep.is_left_censored and not ep.is_right_censored
        assert ep.is_fully_observed

    def test_single_bar_episode(self):
        segment = _build_segment("s", [False, True, False], is_last=False)
        episodes, _ = service._walk_setup_in_segment("s", segment)
        assert len(episodes) == 1
        assert episodes[0].duration_bars == 1

    def test_left_censored_when_true_at_segment_start(self):
        segment = _build_segment("s", [True, True, False], is_last=False)
        episodes, _ = service._walk_setup_in_segment("s", segment)
        assert len(episodes) == 1
        assert episodes[0].is_left_censored
        assert episodes[0].start_timestamp == _iso(0)

    def test_right_censored_at_segment_end_when_more_segments_follow(self):
        segment = _build_segment("s", [False, True, True], is_last=False)
        episodes, _ = service._walk_setup_in_segment("s", segment)
        assert len(episodes) == 1
        assert episodes[0].termination_reason == TerminationReason.SEGMENT_END
        assert episodes[0].is_right_censored
        assert not episodes[0].is_fully_observed

    def test_right_censored_at_dataset_end_when_this_is_the_last_segment(self):
        segment = _build_segment("s", [False, True, True], is_last=True)
        episodes, _ = service._walk_setup_in_segment("s", segment)
        assert len(episodes) == 1
        assert episodes[0].termination_reason == TerminationReason.DATASET_END
        assert episodes[0].is_right_censored

    def test_insufficient_data_closes_and_right_censors_an_active_run(self):
        segment = _build_segment("s", [False, True, None, True], is_last=False)
        episodes, records = service._walk_setup_in_segment("s", segment)
        # bar 1 opens a run, bar 2 (None) closes it as INSUFFICIENT_DATA;
        # bar 3 (True) opens a NEW run, closed at segment end.
        assert len(episodes) == 2
        first, second = episodes
        assert first.duration_bars == 1
        assert first.termination_reason == TerminationReason.INSUFFICIENT_DATA
        assert first.is_right_censored
        assert second.start_timestamp == _iso(3)
        assert second.termination_reason == TerminationReason.SEGMENT_END
        assert not second.is_left_censored  # position 3, not position 0
        assert records[2].computable is False
        assert records[2].insufficient_reason == "test-insufficient"

    def test_no_true_run_produces_no_episodes(self):
        segment = _build_segment("s", [False, False, None, False], is_last=True)
        episodes, records = service._walk_setup_in_segment("s", segment)
        assert episodes == []
        assert len(records) == 4

    def test_multiple_episodes_within_one_segment(self):
        segment = _build_segment("s", [True, False, True, True, False, True], is_last=True)
        episodes, _ = service._walk_setup_in_segment("s", segment)
        assert len(episodes) == 3
        assert episodes[0].is_left_censored and episodes[0].duration_bars == 1
        assert episodes[1].duration_bars == 2 and not episodes[1].is_left_censored
        assert episodes[2].termination_reason == TerminationReason.DATASET_END  # last segment, runs to the end

    def test_activation_bar_and_continuation_bar_counts_from_records(self):
        segment = _build_segment("s", [False, True, True, True, False], is_last=True)
        episodes, records = service._walk_setup_in_segment("s", segment)
        detected_true_bars = sum(1 for r in records if r.detected is True)
        assert len(episodes) == 1  # one activation bar
        assert detected_true_bars == 3  # 1 activation + 2 continuation bars
        assert episodes[0].duration_bars == 3


class TestEpisodesNeverBridgeSegmentBoundary:
    def test_active_run_at_end_of_one_segment_does_not_merge_into_the_next(self):
        # Segment A: active through its own last bar (would-be right-censored).
        segment_a = _build_segment("s", [False, True, True], is_last=False)
        # Segment B: active from its own first bar (would-be left-censored) -
        # built completely independently, no shared state with segment_a.
        segment_b = _build_segment("s", [True, True, False], is_last=True, start_seq=1000)

        episodes_a, _ = service._walk_setup_in_segment("s", segment_a)
        episodes_b, _ = service._walk_setup_in_segment("s", segment_b)

        assert len(episodes_a) == 1 and len(episodes_b) == 1
        assert episodes_a[0].segment_id != episodes_b[0].segment_id
        assert episodes_a[0].is_right_censored and episodes_a[0].termination_reason == TerminationReason.SEGMENT_END
        assert episodes_b[0].is_left_censored
        # Never merged into a single 6-bar episode spanning both segments.
        assert episodes_a[0].duration_bars == 2
        assert episodes_b[0].duration_bars == 2


# ---------------------------------------------------------------------------
# Overlap: the sorted-interval sweep and its containment logic
# ---------------------------------------------------------------------------

class TestEpisodeOverlapSweep:
    def test_simple_partial_overlap(self):
        a = [_episode("a", "seg", 0, 2)]
        b = [_episode("b", "seg", 1, 3)]
        pairs, ia, ib, cab, cba = service._sweep_episode_overlaps(a, b)
        assert (pairs, ia, ib, cab, cba) == (1, 1, 1, 0, 0)

    def test_no_overlap(self):
        a = [_episode("a", "seg", 0, 1)]
        b = [_episode("b", "seg", 5, 6)]
        pairs, ia, ib, cab, cba = service._sweep_episode_overlaps(a, b)
        assert (pairs, ia, ib, cab, cba) == (0, 0, 0, 0, 0)

    def test_full_containment_b_inside_a(self):
        a = [_episode("a", "seg", 0, 10)]
        b = [_episode("b", "seg", 2, 4)]
        pairs, ia, ib, cab, cba = service._sweep_episode_overlaps(a, b)
        assert pairs == 1
        assert cab == 0  # a is not contained in b
        assert cba == 1  # b IS contained in a

    def test_one_long_interval_overlapping_two_shorter_ones(self):
        a = [_episode("a", "seg", 0, 20)]
        b = [_episode("b", "seg", 1, 2), _episode("b", "seg", 5, 6)]
        pairs, ia, ib, cab, cba = service._sweep_episode_overlaps(a, b)
        assert pairs == 2
        assert ia == 1  # a's one episode intersects (with both)
        assert ib == 2  # both of b's episodes intersect
        assert cba == 2  # both b episodes are fully inside a
        assert cab == 0

    def test_touching_endpoints_count_as_overlap(self):
        a = [_episode("a", "seg", 0, 2)]
        b = [_episode("b", "seg", 2, 4)]  # shares the bar at seq=2
        pairs, *_rest = service._sweep_episode_overlaps(a, b)
        assert pairs == 1


class TestActiveBarOverlapAndActivationOverlap:
    def test_active_bar_overlap_metrics(self):
        # 4 jointly-computable bars: A=[T,T,F,F], B=[T,F,T,F]
        a_records = [service.SetupComputabilityRecord(_iso(i), True, d, None) for i, d in enumerate([True, True, False, False])]
        b_records = [service.SetupComputabilityRecord(_iso(i), True, d, None) for i, d in enumerate([True, False, True, False])]
        metrics = service._active_bar_overlap(a_records, b_records)
        assert metrics.jointly_computable_bars == 4
        assert metrics.p_a_active == 0.5 and metrics.p_b_active == 0.5
        assert metrics.p_both_active == 0.25
        assert metrics.conditional_p_a_given_b == 0.5  # both_true(1) / b_true(2)

    def test_non_computable_bars_excluded_from_overlap(self):
        a_records = [
            service.SetupComputabilityRecord(_iso(0), True, True, None),
            service.SetupComputabilityRecord(_iso(1), False, None, "insufficient"),
        ]
        b_records = [
            service.SetupComputabilityRecord(_iso(0), True, True, None),
            service.SetupComputabilityRecord(_iso(1), True, True, None),
        ]
        metrics = service._active_bar_overlap(a_records, b_records)
        assert metrics.jointly_computable_bars == 1  # bar 1 excluded (A not computable there)

    def test_same_bar_activation_overlap(self):
        a = [_episode("a", "seg", 0, 1), _episode("a", "seg", 5, 5)]
        b = [_episode("b", "seg", 0, 2)]  # starts at the same bar as a's first episode
        overlap = service._activation_overlap(a, b)
        assert overlap.same_bar_activation_count == 1
        assert overlap.a_activation_count == 2 and overlap.b_activation_count == 1
        assert overlap.p_same_bar_given_a == 0.5
        assert overlap.p_same_bar_given_b == 1.0


class TestActivationProximity:
    def test_proximity_within_threshold(self):
        a = [_episode("a", "seg", 0, 0), _episode("a", "seg", 10, 10)]  # t=0min, t=50min
        b = [_episode("b", "seg", 2, 2), _episode("b", "seg", 20, 20)]  # t=10min, t=100min
        metrics = service._activation_proximity(a, b, threshold_minutes=15)
        # a@0(0min) has b@2(10min) within 15min -> counts; a@10(50min) has no b within 15min (|50-10|=40, |50-100|=50)
        assert metrics.a_activations_with_nearby_b == 1
        # b@2(10min) has a@0(0min) within 15min -> counts; b@20(100min) has none within 15min
        assert metrics.b_activations_with_nearby_a == 1

    def test_exact_same_bar_counts_as_proximity(self):
        a = [_episode("a", "seg", 5, 5)]
        b = [_episode("b", "seg", 5, 5)]
        metrics = service._activation_proximity(a, b, threshold_minutes=5)
        assert metrics.a_activations_with_nearby_b == 1
        assert metrics.b_activations_with_nearby_a == 1


# ---------------------------------------------------------------------------
# Clustering: within-segment gaps, censored_by_gap, bursts
# ---------------------------------------------------------------------------

class TestClustering:
    def test_within_segment_gap_and_censored_by_gap(self):
        seg1 = [_episode("s", "seg1", 0, 1), _episode("s", "seg1", 5, 5)]
        seg2 = [_episode("s", "seg2", 0, 0)]
        by_segment = {"seg1": seg1, "seg2": seg2}
        gaps, censored = service._within_segment_gaps("s", by_segment)
        assert len(gaps) == 1  # only the pair WITHIN seg1
        # gap from end of episode 1 (seq=1, minute 5) to start of episode 2 (seq=5, minute 25) = 20 minutes
        assert gaps[0].gap_minutes == 20.0
        assert censored == 2  # seg1's last episode + seg2's only (also-last) episode

    def test_bursts_group_close_episodes_and_split_on_large_gaps(self):
        # seq 0-1, then seq 3 (10 min gap, <=15 -> same burst), then seq 20 (95 min gap, >15 -> new burst)
        episodes = [
            _episode("s", "seg", 0, 1),
            _episode("s", "seg", 3, 3),
            _episode("s", "seg", 20, 20),
        ]
        by_segment = service._episodes_by_segment_sorted(episodes)
        burst = service._bursts_for_threshold(by_segment, threshold_minutes=15)
        assert burst.burst_count == 2
        assert burst.burst_sizes == (2, 1)
        assert burst.longest_burst_size == 2

    def test_no_episodes_produces_zero_bursts(self):
        burst = service._bursts_for_threshold({}, threshold_minutes=15)
        assert burst.burst_count == 0
        assert burst.longest_burst_size == 0


# ---------------------------------------------------------------------------
# Transition censoring
# ---------------------------------------------------------------------------

class TestTransitionCensoring:
    def test_censored_at_segment_end_vs_dataset_end(self):
        seg_a_id = _iso(0)  # not the last segment
        seg_b_id = _iso(1000)  # the last segment

        state_a = _market_state(0)
        state_b = _market_state(1000)
        seg_a = service._Segment([state_a], [_rule_output(0)], [_setup_output(0, {})], is_last=False)
        seg_b = service._Segment([state_b], [_rule_output(1000)], [_setup_output(1000, {})], is_last=True)
        assert seg_a.segment_id == seg_a_id and seg_b.segment_id == seg_b_id

        ep_a = _episode("solo", seg_a_id, 0, 0, term=TerminationReason.SEGMENT_END, right=True)
        ep_b = _episode("solo", seg_b_id, 1000, 1000, term=TerminationReason.DATASET_END, right=True)

        dataset = service._Dataset(
            segments=[seg_a, seg_b], setup_names=["solo"],
            episodes_by_setup={"solo": [ep_a, ep_b]}, records_by_setup={"solo": []},
            activation_events=service._build_activation_events([ep_a, ep_b]),
        )
        manifest = service.build_run_manifest(
            config=_dummy_config(), row_count=2,
            generated_at=datetime.now(timezone.utc), source_description="test",
        )
        result = service.build_transitions(dataset, manifest)
        by_start = {t.from_episode_start: t for t in result.transitions}

        assert by_start[ep_a.start_timestamp].censored
        assert by_start[ep_a.start_timestamp].censor_reason == "segment_end"
        assert by_start[ep_b.start_timestamp].censored
        assert by_start[ep_b.start_timestamp].censor_reason == "dataset_end"

    def test_next_activation_event_found_within_same_segment_is_not_censored(self):
        seg_id = _iso(0)
        state = _market_state(0)
        seg = service._Segment([state], [_rule_output(0)], [_setup_output(0, {})], is_last=True)

        ep_a = _episode("a", seg_id, 0, 0, term=TerminationReason.BECAME_FALSE)
        ep_b = _episode("b", seg_id, 3, 3, term=TerminationReason.DATASET_END, right=True)  # activates after a ends

        dataset = service._Dataset(
            segments=[seg], setup_names=["a", "b"],
            episodes_by_setup={"a": [ep_a], "b": [ep_b]}, records_by_setup={"a": [], "b": []},
            activation_events=service._build_activation_events([ep_a, ep_b]),
        )
        manifest = service.build_run_manifest(
            config=_dummy_config(), row_count=2,
            generated_at=datetime.now(timezone.utc), source_description="test",
        )
        result = service.build_transitions(dataset, manifest)
        transition_from_a = next(t for t in result.transitions if t.from_setup == "a")
        assert not transition_from_a.censored
        assert transition_from_a.to_activated_setups == ("b",)
        assert transition_from_a.time_to_next_minutes == 15.0  # seq 0 -> seq 3, 3*5min


def _dummy_config():
    from atlas.profiling.models import ProfilingRunConfig
    return ProfilingRunConfig(
        symbol=Symbol("MNQ1!"), timeframe=Timeframe.M5,
        start=_BASE_TIME, end=_BASE_TIME + timedelta(hours=1), limit=10,
    )
