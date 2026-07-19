import pytest

from atlas.core.errors import InvalidSymbolError, OffTickError
from atlas.core.primitives import Price, Session, Symbol, Timeframe


class TestSymbol:
    def test_valid_symbol(self):
        assert Symbol("MNQU6").ticker == "MNQU6"

    def test_strips_whitespace(self):
        assert Symbol("  MNQU6  ").ticker == "MNQU6"

    def test_str_conversion(self):
        assert str(Symbol("MNQU6")) == "MNQU6"

    def test_blank_symbol_rejected(self):
        with pytest.raises(InvalidSymbolError):
            Symbol("")

    def test_whitespace_only_symbol_rejected(self):
        with pytest.raises(InvalidSymbolError):
            Symbol("   ")

    def test_equality(self):
        assert Symbol("MNQU6") == Symbol("MNQU6")
        assert Symbol("MNQU6") != Symbol("MNQZ6")

    def test_hashable(self):
        # frozen dataclass must be usable as a dict key / set member
        assert len({Symbol("MNQU6"), Symbol("MNQU6"), Symbol("MNQZ6")}) == 2


class TestPrice:
    def test_on_tick_value_accepted(self):
        p = Price(value=20125.75, tick_size=0.25)
        assert p.value == 20125.75
        assert float(p) == 20125.75

    def test_off_tick_value_rejected_not_rounded(self):
        with pytest.raises(OffTickError):
            Price(value=20125.80, tick_size=0.25)

    def test_off_tick_error_message_names_nearest_valid_price(self):
        with pytest.raises(OffTickError, match="20125.75"):
            Price(value=20125.80, tick_size=0.25)

    def test_floating_point_tolerance_does_not_admit_genuinely_off_tick_values(self):
        # 0.1 + 0.2 != 0.3 exactly in floating point - the tolerance must absorb
        # representation error without becoming a rounding allowance.
        p = Price(value=0.1 + 0.2, tick_size=0.1)
        assert abs(p.value - 0.3) < 1e-9

    def test_zero_tick_size_rejected(self):
        with pytest.raises(OffTickError):
            Price(value=100.0, tick_size=0.0)

    def test_negative_tick_size_rejected(self):
        with pytest.raises(OffTickError):
            Price(value=100.0, tick_size=-0.25)

    def test_round_to_tick_snaps_to_nearest(self):
        assert Price.round_to_tick(20125.80, 0.25) == 20125.75
        assert Price.round_to_tick(20125.90, 0.25) == 20126.00

    def test_round_to_tick_does_not_raise(self):
        # the whole point of round_to_tick is that it's an explicit opt-in,
        # never implicitly invoked by the constructor
        Price.round_to_tick(999999.123, 0.25)

    def test_equality(self):
        assert Price(20125.75, 0.25) == Price(20125.75, 0.25)
        assert Price(20125.75, 0.25) != Price(20125.50, 0.25)


class TestTimeframe:
    def test_duration_minutes(self):
        assert Timeframe.M1.duration_minutes == 1
        assert Timeframe.M5.duration_minutes == 5
        assert Timeframe.M15.duration_minutes == 15
        assert Timeframe.H1.duration_minutes == 60

    def test_value_matches_wire_format(self):
        # these string values are what adapters will see on the wire later -
        # pin them explicitly so a future refactor can't silently change them
        assert Timeframe.M1.value == "1m"
        assert Timeframe.M5.value == "5m"
        assert Timeframe.M15.value == "15m"
        assert Timeframe.H1.value == "1h"

    def test_constructible_from_wire_value(self):
        assert Timeframe("5m") is Timeframe.M5


class TestSession:
    def test_members_exist(self):
        assert Session.RTH.value == "RTH"
        assert Session.OVERNIGHT.value == "OVERNIGHT"
        assert Session.NY.value == "NY"
        assert Session.LONDON.value == "LONDON"

    def test_constructible_from_wire_value(self):
        assert Session("RTH") is Session.RTH
