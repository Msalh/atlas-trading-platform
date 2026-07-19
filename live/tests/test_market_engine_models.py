from datetime import datetime, timezone

import pytest

from atlas.core.events import Event
from atlas.core.primitives import Price, Symbol, Timeframe
from atlas.market_engine.errors import MarketEngineValidationError
from atlas.market_engine.models import BarStatus, MarketEventType, MarketState


def _envelope(event_type="bar_closed"):
    return Event(
        event_type=event_type,
        source="tradingview",
        occurred_at=datetime(2026, 7, 18, 13, 35, 0, tzinfo=timezone.utc),
    )


def _minimal_state(**overrides):
    fields = dict(
        envelope=_envelope(),
        schema_version="1.0",
        symbol=Symbol("MNQU6"),
        timeframe=Timeframe.M5,
        bar_status=BarStatus.CLOSED,
    )
    fields.update(overrides)
    return MarketState(**fields)


class TestMarketStateConstruction:
    def test_minimal_construction_succeeds(self):
        state = _minimal_state()
        assert state.symbol == Symbol("MNQU6")
        assert state.timeframe == Timeframe.M5
        assert state.bar_status == BarStatus.CLOSED

    def test_every_optional_field_defaults_to_none_not_fabricated(self):
        state = _minimal_state()
        assert state.open is None
        assert state.vwap is None
        assert state.nearest_liquidity_type is None
        assert state.trend_1h is None
        assert state.liquidity_sweep is None

    def test_fully_populated_construction(self):
        state = _minimal_state(
            open=Price(20120.00, 0.25),
            high=Price(20128.50, 0.25),
            low=Price(20118.00, 0.25),
            close=Price(20125.75, 0.25),
            volume=4210,
            vwap=Price(20118.50, 0.25),
            liquidity_sweep=False,
            reclaim=True,
        )
        assert state.close.value == 20125.75
        assert state.reclaim is True
        assert state.liquidity_sweep is False

    def test_immutable(self):
        state = _minimal_state()
        with pytest.raises(Exception):
            state.symbol = Symbol("MNQZ6")


class TestEventTypeProperty:
    def test_event_type_reads_from_envelope(self):
        state = _minimal_state(envelope=_envelope("reclaim"))
        assert state.event_type == MarketEventType.RECLAIM

    def test_bar_closed_is_the_default_envelope_event_type(self):
        state = _minimal_state()
        assert state.event_type == MarketEventType.BAR_CLOSED

    def test_illegal_event_type_rejected_at_construction(self):
        with pytest.raises(MarketEngineValidationError):
            _minimal_state(envelope=_envelope("not_a_real_event_type"))

    def test_all_seven_named_event_types_are_constructible(self):
        for et in MarketEventType:
            state = _minimal_state(envelope=_envelope(et.value))
            assert state.event_type == et

    def test_event_type_and_flags_can_coexist(self):
        # event_type carries the headline signal; flags carry co-occurring
        # secondary conditions - both may be true at once, deliberately.
        state = _minimal_state(envelope=_envelope("reclaim"), volume_spike=True)
        assert state.event_type == MarketEventType.RECLAIM
        assert state.volume_spike is True


class TestSchemaVersion:
    def test_blank_schema_version_rejected(self):
        with pytest.raises(MarketEngineValidationError):
            _minimal_state(schema_version="")

    def test_whitespace_only_schema_version_rejected(self):
        with pytest.raises(MarketEngineValidationError):
            _minimal_state(schema_version="   ")

    def test_any_nonblank_schema_version_accepted(self):
        # Sprint 2's deliberately minimal policy - see translator module
        # docstring for what's deferred, not decided here.
        assert _minimal_state(schema_version="1.0").schema_version == "1.0"
        assert _minimal_state(schema_version="1.1").schema_version == "1.1"
