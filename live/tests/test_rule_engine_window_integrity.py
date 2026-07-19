from datetime import datetime, timedelta, timezone

import pytest

from atlas.core.events import Event
from atlas.core.primitives import Symbol, Timeframe
from atlas.market_engine.models import BarStatus, MarketState
from atlas.rule_engine.window_integrity import (
    DuplicateTimestampError,
    EmptyWindowError,
    MixedSymbolError,
    MixedTimeframeError,
    NonMonotonicTimestampError,
    WindowGapError,
    WindowIntegrityError,
    validate_market_state_window,
)


def _state(event_id="e1", occurred_at="2026-07-18T13:35:00", symbol="MNQU6", timeframe=Timeframe.M5):
    return MarketState(
        envelope=Event(
            event_type="bar_closed",
            source="tradingview",
            occurred_at=datetime.fromisoformat(occurred_at).replace(tzinfo=timezone.utc),
            event_id=event_id,
        ),
        schema_version="1.0",
        symbol=Symbol(symbol),
        timeframe=timeframe,
        bar_status=BarStatus.CLOSED,
    )


def _contiguous_window(count, base_time="2026-07-18T13:00:00", minutes=5, timeframe=Timeframe.M5):
    base = datetime.fromisoformat(base_time)
    return [
        _state(event_id=f"e{i}", occurred_at=(base + timedelta(minutes=minutes * i)).isoformat(), timeframe=timeframe)
        for i in range(count)
    ]


class TestValidateMarketStateWindow:
    def test_empty_window_raises_empty_window_error(self):
        with pytest.raises(EmptyWindowError):
            validate_market_state_window([])

    def test_single_bar_window_is_valid(self):
        validate_market_state_window(_contiguous_window(1))  # must not raise

    def test_valid_contiguous_window_does_not_raise(self):
        validate_market_state_window(_contiguous_window(20))  # must not raise

    def test_mixed_symbol_raises_mixed_symbol_error(self):
        window = _contiguous_window(2)
        window[1] = _state(event_id="e1b", occurred_at=window[1].envelope.occurred_at.isoformat(), symbol="ESU6")
        with pytest.raises(MixedSymbolError):
            validate_market_state_window(window)

    def test_mixed_timeframe_raises_mixed_timeframe_error(self):
        window = _contiguous_window(2)
        window[1] = _state(
            event_id="e1b", occurred_at=window[1].envelope.occurred_at.isoformat(), timeframe=Timeframe.M1,
        )
        with pytest.raises(MixedTimeframeError):
            validate_market_state_window(window)

    def test_duplicate_timestamp_raises_duplicate_timestamp_error(self):
        window = _contiguous_window(2)
        window[1] = _state(event_id="e1b", occurred_at=window[0].envelope.occurred_at.isoformat())
        with pytest.raises(DuplicateTimestampError):
            validate_market_state_window(window)

    def test_out_of_order_timestamp_raises_non_monotonic_timestamp_error(self):
        first = _state(event_id="e0", occurred_at="2026-07-18T13:00:00")
        earlier = _state(
            event_id="e1", occurred_at=(first.envelope.occurred_at - timedelta(minutes=5)).isoformat(),
        )
        with pytest.raises(NonMonotonicTimestampError):
            validate_market_state_window([first, earlier])

    def test_larger_than_cadence_gap_raises_window_gap_error(self):
        window = _contiguous_window(2)
        late = _state(
            event_id="e1b",
            occurred_at=(window[0].envelope.occurred_at + timedelta(minutes=10)).isoformat(),
        )
        with pytest.raises(WindowGapError):
            validate_market_state_window([window[0], late])

    def test_smaller_than_cadence_gap_raises_window_gap_error(self):
        window = _contiguous_window(2)
        early = _state(
            event_id="e1b",
            occurred_at=(window[0].envelope.occurred_at + timedelta(minutes=2)).isoformat(),
        )
        with pytest.raises(WindowGapError):
            validate_market_state_window([window[0], early])

    def test_weekend_gap_is_not_treated_specially_and_still_raises(self):
        # Friday close to Sunday open - a real, expected market closure. This
        # module deliberately has no session/calendar awareness (see its
        # module docstring): the gap is rejected exactly like any other.
        friday_close = _state(event_id="e0", occurred_at="2026-07-17T20:55:00")
        sunday_open = _state(event_id="e1", occurred_at="2026-07-19T22:00:00")
        with pytest.raises(WindowGapError):
            validate_market_state_window([friday_close, sunday_open])

    def test_hourly_timeframe_uses_its_own_cadence(self):
        window = _contiguous_window(3, minutes=60, timeframe=Timeframe.H1)
        validate_market_state_window(window)  # must not raise

    def test_does_not_mutate_or_reorder_caller_input(self):
        first = _state(event_id="e0", occurred_at="2026-07-18T13:00:00")
        earlier = _state(
            event_id="e1", occurred_at=(first.envelope.occurred_at - timedelta(minutes=5)).isoformat(),
        )
        window = [first, earlier]
        before = list(window)
        with pytest.raises(NonMonotonicTimestampError):
            validate_market_state_window(window)
        assert window == before

    def test_all_specific_errors_are_window_integrity_errors(self):
        assert issubclass(EmptyWindowError, WindowIntegrityError)
        assert issubclass(MixedSymbolError, WindowIntegrityError)
        assert issubclass(MixedTimeframeError, WindowIntegrityError)
        assert issubclass(NonMonotonicTimestampError, WindowIntegrityError)
        assert issubclass(DuplicateTimestampError, WindowIntegrityError)
        assert issubclass(WindowGapError, WindowIntegrityError)
