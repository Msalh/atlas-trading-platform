import json
from datetime import datetime, timedelta, timezone

from atlas.core.events import Event
from atlas.core.primitives import Price, Symbol, Timeframe
from atlas.market_engine.models import BarStatus, MarketState
from atlas.rule_engine.models import FactResult
from atlas.rule_engine.models import InsufficientData as FactInsufficientData
from atlas.rule_engine.models import RuleEngineOutput
from atlas.rule_engine.service import build_rule_engine_output_window
from atlas.setup_engine.models import InsufficientData, SetupEvaluationContext, SetupFamily, SetupResult, Severity
from atlas.setup_engine.registry import REGISTRY, required_history, validate_registry
from atlas.setup_engine.service import build_setup_engine_output, setup_engine_output_to_dict
from atlas.setup_engine.setups.sustained_displacement_streak import (
    DEFAULT_SUSTAINED_DISPLACEMENT_STREAK_DEFINITION,
    SUSTAINED_DISPLACEMENT_STREAK_REGISTRATION,
    evaluate_sustained_displacement_streak,
)


def _displacement(value=True, ratio=2.0, threshold=1.5):
    return FactResult(fact_name="displacement", definition_version="1.0", value=value, evidence={"range_atr_ratio": ratio, "threshold": threshold})


def _displacement_insufficient(reason="atr is zero"):
    return FactInsufficientData(fact_name="displacement", definition_version="1.0", reason=reason)


def _outcome(entry):
    """True -> a computed displacement=True; False -> computed displacement=False;
    None -> insufficient_data; anything else is passed through unchanged."""
    if entry is True:
        return _displacement(value=True)
    if entry is False:
        return _displacement(value=False)
    if entry is None:
        return _displacement_insufficient()
    return entry


def _history(entries, base_time="2026-07-18T13:00:00"):
    base = datetime.fromisoformat(base_time)
    return [
        RuleEngineOutput(
            schema_version="1.0", symbol="MNQU6", timeframe="5m",
            occurred_at=(base + timedelta(minutes=5 * i)).isoformat(),
            facts={"displacement": _outcome(entry)},
        )
        for i, entry in enumerate(entries)
    ]


def _context(entries):
    return SetupEvaluationContext(history=_history(entries))


def _evaluate(context):
    return evaluate_sustained_displacement_streak(context, DEFAULT_SUSTAINED_DISPLACEMENT_STREAK_DEFINITION)


class TestRegistration:
    def test_registered_in_the_real_registry(self):
        assert SUSTAINED_DISPLACEMENT_STREAK_REGISTRATION in REGISTRY

    def test_definition_family_is_momentum(self):
        assert DEFAULT_SUSTAINED_DISPLACEMENT_STREAK_DEFINITION.family == SetupFamily.MOMENTUM

    def test_required_facts_are_displacement_only(self):
        assert SUSTAINED_DISPLACEMENT_STREAK_REGISTRATION.required_facts == ("displacement",)

    def test_required_history_is_two(self):
        assert SUSTAINED_DISPLACEMENT_STREAK_REGISTRATION.required_history == 2

    def test_real_registry_passes_validation(self):
        validate_registry(REGISTRY)  # must not raise

    def test_real_registry_required_history_reflects_the_new_maximum(self):
        # The other two registered setups only need 1 bar - this one raises
        # the registry-wide maximum to 2, proving the aggregate genuinely
        # reflects each registration's own required_history, not a stale
        # cached value.
        assert required_history(REGISTRY) == 2


class TestInsufficientHistory:
    def test_history_shorter_than_min_streak_length_is_insufficient_even_if_true(self):
        outcome = _evaluate(_context([True]))  # only 1 bar, below required_history=2
        assert isinstance(outcome, InsufficientData)
        assert "fewer than 2 bars" in outcome.reason
        assert "got 1" in outcome.reason

    def test_empty_but_valid_context_is_never_reachable_below_required_history(self):
        # SetupEvaluationContext itself refuses empty history (Sprint 17B) -
        # the shortest constructible context here is 1 bar, already covered
        # above.
        outcome = _evaluate(_context([False]))
        assert isinstance(outcome, InsufficientData)


class TestCurrentBarInsufficientData:
    def test_current_bar_insufficient_data_propagates_its_reason(self):
        outcome = _evaluate(_context([True, None]))
        assert isinstance(outcome, InsufficientData)
        assert "displacement is insufficient_data on the current bar" in outcome.reason
        assert "atr is zero" in outcome.reason


class TestNegativeDetection:
    def test_current_bar_false_is_not_detected(self):
        outcome = _evaluate(_context([True, False]))
        assert isinstance(outcome, SetupResult)
        assert outcome.detected is False
        assert outcome.severity is None
        assert outcome.evidence.supporting_facts == ()

    def test_all_false_not_detected(self):
        outcome = _evaluate(_context([False, False]))
        assert outcome.detected is False
        assert outcome.evidence.supporting_facts == ()


class TestBrokenStreak:
    def test_streak_broken_by_a_false_bar_only_counts_the_trailing_run(self):
        outcome = _evaluate(_context([True, False, True, True]))
        assert outcome.detected is True
        assert len(outcome.evidence.supporting_facts) == 2
        assert dict(outcome.evidence.supporting_facts[0].detail)["streak_length"] == 2

    def test_streak_broken_by_an_insufficient_bar_only_counts_the_trailing_run(self):
        outcome = _evaluate(_context([True, None, True, True]))
        assert outcome.detected is True
        assert len(outcome.evidence.supporting_facts) == 2
        assert dict(outcome.evidence.supporting_facts[0].detail)["streak_length"] == 2


class TestExactlyTwoBarStreak:
    def test_exactly_two_bar_streak_detects(self):
        outcome = _evaluate(_context([True, True]))
        assert isinstance(outcome, SetupResult)
        assert outcome.detected is True
        assert outcome.severity == Severity.NORMAL
        assert len(outcome.evidence.supporting_facts) == 2
        assert dict(outcome.evidence.supporting_facts[0].detail)["streak_length"] == 2
        assert dict(outcome.evidence.supporting_facts[1].detail)["streak_length"] == 2


class TestLongerStreak:
    def test_four_bar_streak_reports_the_real_length_not_capped_at_the_minimum(self):
        outcome = _evaluate(_context([True, True, True, True]))
        assert outcome.detected is True
        assert len(outcome.evidence.supporting_facts) == 4
        for fact in outcome.evidence.supporting_facts:
            assert dict(fact.detail)["streak_length"] == 4

    def test_leading_unrelated_false_bar_does_not_shrink_a_valid_trailing_streak(self):
        outcome = _evaluate(_context([False, True, True, True]))
        assert outcome.detected is True
        assert len(outcome.evidence.supporting_facts) == 3
        assert dict(outcome.evidence.supporting_facts[0].detail)["streak_length"] == 3


class TestEvidence:
    def test_evidence_is_one_entry_per_streak_bar_in_chronological_order(self):
        context = _context([True, True, True])
        outcome = _evaluate(context)
        occurred_ats = [f.occurred_at for f in outcome.evidence.supporting_facts]
        assert occurred_ats == sorted(occurred_ats)
        assert occurred_ats[-1] == context.current.occurred_at

    def test_evidence_detail_preserves_the_original_displacement_evidence(self):
        context = _context([_displacement(value=True, ratio=3.5, threshold=1.5), _displacement(value=True, ratio=4.0, threshold=1.5)])
        outcome = _evaluate(context)
        first, second = outcome.evidence.supporting_facts
        assert dict(first.detail) == {"range_atr_ratio": 3.5, "threshold": 1.5, "streak_length": 2}
        assert dict(second.detail) == {"range_atr_ratio": 4.0, "threshold": 1.5, "streak_length": 2}

    def test_every_supporting_fact_is_named_displacement(self):
        outcome = _evaluate(_context([True, True, True]))
        assert all(f.fact_name == "displacement" for f in outcome.evidence.supporting_facts)

    def test_no_streak_produces_empty_evidence(self):
        outcome = _evaluate(_context([True, False]))
        assert outcome.evidence.supporting_facts == ()


class TestSerialization:
    def test_complete_output_is_json_dumps_safe(self):
        context = _context([True, True, True])
        output = build_setup_engine_output(context, registry=(SUSTAINED_DISPLACEMENT_STREAK_REGISTRATION,))
        json.dumps(setup_engine_output_to_dict(output))  # must not raise

    def test_insufficient_history_serializes_cleanly(self):
        context = _context([True])
        output = build_setup_engine_output(context, registry=(SUSTAINED_DISPLACEMENT_STREAK_REGISTRATION,))
        as_dict = setup_engine_output_to_dict(output)
        assert as_dict["setups"] == [{
            "name": "sustained_displacement_streak", "status": "insufficient_data",
            "definition_version": "1.0", "reason": "fewer than 2 bars available in history (got 1)",
        }]


class TestDeterminism:
    def test_same_context_same_output(self):
        context = _context([True, True, True])
        assert _evaluate(context) == _evaluate(context)


class TestRequiredHistoryAndWindowBoundaries:
    def test_required_history_is_exactly_two(self):
        assert SUSTAINED_DISPLACEMENT_STREAK_REGISTRATION.required_history == 2

    def test_history_below_required_history_is_always_insufficient_even_if_true(self):
        outcome = _evaluate(_context([True]))
        assert isinstance(outcome, InsufficientData)

    def test_history_at_exactly_required_history_can_detect(self):
        outcome = _evaluate(_context([True, True]))
        assert isinstance(outcome, SetupResult) and outcome.detected is True

    def test_older_bars_beyond_the_true_streak_do_not_extend_or_shrink_it(self):
        outcome = _evaluate(_context([False, True, True, True]))
        assert outcome.detected is True
        assert dict(outcome.evidence.supporting_facts[0].detail)["streak_length"] == 3

    def test_the_walk_stops_at_the_exact_first_disqualifying_bar(self):
        # oldest[0]=True, [1]=True, [2]=False, [3]=True, [4]=True(current) -
        # the walk must stop exactly at index 2, never reaching index 0/1.
        outcome = _evaluate(_context([True, True, False, True, True]))
        assert outcome.detected is True
        assert len(outcome.evidence.supporting_facts) == 2
        assert dict(outcome.evidence.supporting_facts[0].detail)["streak_length"] == 2

    def test_deterministic_across_repeated_evaluation(self):
        context = _context([True, True, True, True, True])
        results = [_evaluate(context) for _ in range(3)]
        assert results[0] == results[1] == results[2]


def _market_state(event_id, occurred_at):
    return MarketState(
        envelope=Event(event_type="bar_closed", source="tradingview", occurred_at=occurred_at, event_id=event_id),
        schema_version="1.0", symbol=Symbol("MNQU6"), timeframe=Timeframe.M5, bar_status=BarStatus.CLOSED,
        high=Price(20140.00, 0.25), low=Price(20120.00, 0.25), atr=10.0,
        open=Price(20126.00, 0.25), close=Price(20125.00, 0.25), volume_ratio=0.5,
    )


class TestEndToEnd:
    def test_end_to_end_using_the_real_registry(self):
        base = datetime.fromisoformat("2026-07-18T13:00:00")
        window = [
            _market_state(f"e{i}", (base + timedelta(minutes=5 * i)).replace(tzinfo=timezone.utc))
            for i in range(3)
        ]
        # every bar: (high-low)/atr = 20/10 = 2.0 > 1.5 -> displacement=True on all 3 bars
        context = SetupEvaluationContext(history=build_rule_engine_output_window(window))
        output = build_setup_engine_output(context, registry=REGISTRY)

        by_name = {s.setup_name: s for s in output.setups}
        result = by_name["sustained_displacement_streak"]
        assert isinstance(result, SetupResult)
        assert result.detected is True
        assert result.severity == Severity.NORMAL
        assert len(result.evidence.supporting_facts) == 3
        assert dict(result.evidence.supporting_facts[0].detail)["streak_length"] == 3
