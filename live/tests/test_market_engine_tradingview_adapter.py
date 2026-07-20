import pytest
from pydantic import ValidationError

from atlas.core.errors import OffTickError
from atlas.core.primitives import Session, Symbol, Timeframe
from atlas.market_engine.adapters.tradingview.translator import to_canonical
from atlas.market_engine.adapters.tradingview.wire_models import TradingViewMarketStatePayload
from atlas.market_engine.errors import MarketEngineValidationError
from atlas.market_engine.models import BarStatus, MarketEventType


def _payload(**overrides):
    fields = dict(
        schema_version="1.0",
        event_id="MNQU6:5m:2026-07-18T13:35:00Z",
        symbol="MNQU6",
        source="tradingview",
        timeframe="5m",
        timestamp="2026-07-18T13:35:00Z",
        bar_status="closed",
    )
    fields.update(overrides)
    return TradingViewMarketStatePayload(**fields)


class TestWireModelValidation:
    def test_minimal_valid_payload_accepted(self):
        p = _payload()
        assert p.symbol == "MNQU6"
        assert p.event_type == "bar_closed"  # default

    def test_unknown_extra_field_tolerated(self):
        p = TradingViewMarketStatePayload.model_validate(
            {**_payload().model_dump(), "some_future_field": "whatever"}
        )
        assert p.symbol == "MNQU6"

    def test_wrong_type_on_known_field_rejected(self):
        with pytest.raises(ValidationError):
            TradingViewMarketStatePayload.model_validate({**_payload().model_dump(), "open": "not-a-number"})

    @pytest.mark.parametrize("field", ["schema_version", "event_id", "symbol", "timeframe"])
    def test_blank_required_identity_field_rejected(self, field):
        with pytest.raises(ValidationError):
            TradingViewMarketStatePayload.model_validate({**_payload().model_dump(), field: ""})

    def test_missing_required_field_rejected(self):
        with pytest.raises(ValidationError):
            TradingViewMarketStatePayload(
                schema_version="1.0", event_id="x", symbol="MNQU6", timeframe="5m",
                # timestamp and bar_status missing
            )

    def test_illegal_bar_status_rejected(self):
        with pytest.raises(ValidationError):
            TradingViewMarketStatePayload.model_validate({**_payload().model_dump(), "bar_status": "half_open"})

    def test_every_optional_field_explicitly_none_by_default(self):
        p = _payload()
        assert p.open is None
        assert p.vwap is None
        assert p.trend_1h is None
        assert p.liquidity_sweep is None


class TestSchemaVersionTolerance:
    def test_1_0_accepted(self):
        assert to_canonical(_payload(schema_version="1.0")).schema_version == "1.0"

    def test_1_1_accepted(self):
        assert to_canonical(_payload(schema_version="1.1")).schema_version == "1.1"

    def test_blank_rejected_at_wire_layer(self):
        with pytest.raises(ValidationError):
            _payload(schema_version="")


class TestTickSizeRejection:
    def test_on_tick_price_translates_successfully(self):
        state = to_canonical(_payload(close=20125.75))
        assert state.close.value == 20125.75

    def test_off_tick_price_rejected_at_translation(self):
        with pytest.raises(OffTickError):
            to_canonical(_payload(close=20125.80))

    def test_off_tick_rejection_applies_to_every_tradable_price_field(self):
        # vwap deliberately excluded - Sprint 26: it is a running
        # volume-weighted AVERAGE (analytical), not a traded print, and must
        # never be tick-validated - see test_vwap_is_never_tick_validated
        # below.
        for field in ("open", "high", "low", "close", "rth_open", "previous_day_high",
                      "previous_day_low", "overnight_high", "overnight_low",
                      "nearest_liquidity_level"):
            with pytest.raises(OffTickError):
                to_canonical(_payload(**{field: 20125.80}))

    def test_vwap_is_never_tick_validated(self):
        # Sprint 26 root-cause fix: vwap is Pine's ta.vwap, a continuous
        # running average - it will almost never land on the tick grid, and
        # rejecting it here was the actual production bug (1197/1200 real
        # historical bars rejected on this field alone). Preserved exactly,
        # not rounded, not rejected - the same treatment atr/volume_ratio/
        # distance_from_vwap_points already correctly receive.
        state = to_canonical(_payload(vwap=20125.80123456))
        assert state.vwap == 20125.80123456


class TestExplicitNullHandling:
    def test_absent_optional_price_field_translates_to_none_not_fabricated(self):
        state = to_canonical(_payload())
        assert state.close is None
        assert state.vwap is None
        assert state.nearest_liquidity_level is None

    def test_absent_optional_non_price_field_translates_to_none(self):
        state = to_canonical(_payload())
        assert state.trend_1h is None
        assert state.liquidity_sweep is None
        assert state.session_name is None
        assert state.trading_date is None

    def test_present_zero_is_not_treated_as_absent(self):
        # 0 is a legitimate value (volume=0, distance_to_liquidity_ticks=0) -
        # must not be conflated with "field was absent".
        state = to_canonical(_payload(volume=0, distance_to_liquidity_ticks=0))
        assert state.volume == 0
        assert state.distance_to_liquidity_ticks == 0


class TestTranslationCorrectness:
    def test_full_payload_translates_correctly(self):
        payload = _payload(
            event_type="reclaim",
            open=20120.00, high=20128.50, low=20118.00, close=20125.75, volume=4210,
            session_name="NY", is_rth=True, trading_date="2026-07-18",
            rth_open=20100.00, previous_day_high=20180.00, previous_day_low=20050.25,
            overnight_high=20140.00, overnight_low=20080.50,
            vwap=20118.50, distance_from_vwap_points=7.35, atr=42.5, volume_ratio=1.35,
            nearest_liquidity_level=20180.00, nearest_liquidity_type="previous_day_high",
            distance_to_liquidity_ticks=217, overnight_high_status="untested",
            overnight_low_status="reclaimed", previous_day_high_status="untested",
            previous_day_low_status="swept",
            trend_1m="up", trend_5m="up", trend_15m="flat", trend_1h="down",
            liquidity_sweep=False, reclaim=True, rejection=False, displacement=False,
            volume_spike=False,
        )
        state = to_canonical(payload)

        assert state.event_type == MarketEventType.RECLAIM
        assert state.symbol == Symbol("MNQU6")
        assert state.timeframe == Timeframe.M5
        assert state.bar_status == BarStatus.CLOSED
        assert state.close.value == 20125.75
        assert state.volume == 4210
        assert state.session_name == Session.NY
        assert state.is_rth is True
        assert state.trading_date.isoformat() == "2026-07-18"
        assert state.vwap == 20118.50
        assert state.nearest_liquidity_type == "previous_day_high"
        assert state.trend_1h == "down"
        assert state.reclaim is True
        assert state.liquidity_sweep is False

    def test_timestamp_with_z_suffix_parses_as_utc(self):
        state = to_canonical(_payload(timestamp="2026-07-18T13:35:00Z"))
        assert state.envelope.occurred_at.isoformat() == "2026-07-18T13:35:00+00:00"

    def test_timestamp_with_explicit_offset_parses(self):
        state = to_canonical(_payload(timestamp="2026-07-18T13:35:00+00:00"))
        assert state.envelope.occurred_at.isoformat() == "2026-07-18T13:35:00+00:00"

    def test_malformed_timestamp_rejected(self):
        with pytest.raises(MarketEngineValidationError):
            to_canonical(_payload(timestamp="not-a-timestamp"))

    def test_timestamp_with_no_timezone_marker_rejected(self):
        # distinct failure path from "malformed": this parses fine as a naive
        # datetime, and must still be rejected rather than silently assumed
        # to be UTC.
        with pytest.raises(MarketEngineValidationError, match="no timezone information"):
            to_canonical(_payload(timestamp="2026-07-18T13:35:00"))

    def test_event_id_preserved_through_translation(self):
        state = to_canonical(_payload(event_id="MNQU6:5m:2026-07-18T13:35:00Z"))
        assert state.envelope.event_id == "MNQU6:5m:2026-07-18T13:35:00Z"

    def test_received_at_is_stamped_at_translation_time_not_from_wire(self):
        # TradingViewMarketStatePayload has no received_at field at all - the
        # system stamps it, the wire payload can never claim it.
        state = to_canonical(_payload())
        assert state.envelope.received_at is not None
        assert state.envelope.received_at >= state.envelope.occurred_at

    def test_illegal_event_type_on_wire_rejected_at_translation(self):
        with pytest.raises(MarketEngineValidationError):
            to_canonical(_payload(event_type="not_a_real_event_type"))
