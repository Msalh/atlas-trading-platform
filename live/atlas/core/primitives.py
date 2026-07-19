"""
Domain primitives shared by every future atlas package. Deliberately minimal -
this Sprint's roadmap entry names exactly Symbol, Price, Timeframe, and Session;
nothing here goes further than that. In particular:

  - Price has no arithmetic (subtraction, comparison beyond equality) yet. A
    future package that needs it (e.g. market_engine computing
    distance_from_vwap_points) adds that when it has a real, specific need to
    satisfy - guessing the "right" arithmetic semantics now, with no real
    consumer to check them against, is exactly the speculative-abstraction risk
    the project charter warns against.
  - Session identifies a session by NAME only (RTH/OVERNIGHT/NY/LONDON). It does
    not compute session boundaries, holidays, or DST behavior - that is
    atlas.market_engine's responsibility, built against real session-boundary
    requirements in a later Sprint, not guessed at here.
"""
from dataclasses import dataclass
from enum import Enum

from atlas.core.errors import InvalidSymbolError, OffTickError


@dataclass(frozen=True)
class Symbol:
    """An instrument ticker (e.g. "MNQU6", "MNQ1!"), as a domain type rather than
    a bare str - lets every later package type-check against "this is a symbol"
    instead of "this happens to be a string"."""

    ticker: str

    def __post_init__(self) -> None:
        if not self.ticker or not self.ticker.strip():
            raise InvalidSymbolError("Symbol ticker must not be blank")
        # dataclass is frozen - object.__setattr__ is the documented way to
        # normalize a field during __post_init__ without breaking immutability.
        object.__setattr__(self, "ticker", self.ticker.strip())

    def __str__(self) -> str:
        return self.ticker


@dataclass(frozen=True)
class Price:
    """A price value, validated against an explicit tick size at construction.
    Rejects off-tick values outright - it never silently rounds. Deliberately
    not tied to an instrument/point-value registry (no such registry exists yet,
    and building one ahead of a real multi-instrument need would violate the
    project's no-speculative-abstraction rule) - callers supply the tick size
    they already know."""

    value: float
    tick_size: float

    def __post_init__(self) -> None:
        if self.tick_size <= 0:
            raise OffTickError(f"tick_size must be positive, got {self.tick_size!r}")
        ticks = self.value / self.tick_size
        # Floating-point tolerance, not a rounding allowance: 1e-6 is far smaller
        # than any real tick size this system will ever use (0.25 for MNQ/NQ),
        # so this only absorbs float representation error, never a genuinely
        # off-tick input.
        if abs(ticks - round(ticks)) > 1e-6:
            nearest = Price.round_to_tick(self.value, self.tick_size)
            raise OffTickError(
                f"price {self.value!r} is not on the {self.tick_size!r} tick grid "
                f"(nearest valid price would be {nearest!r}) - rejected, not rounded"
            )

    @staticmethod
    def round_to_tick(value: float, tick_size: float) -> float:
        """Snaps an arbitrary float onto the nearest tick. Same convention
        already used by tools/research/execution_model.py's round_to_tick
        (round(value / tick) * tick) - reused here, not redefined. An explicit
        opt-in utility for callers that want to snap a value; never called
        implicitly by the constructor above, which rejects instead."""
        return round(value / tick_size) * tick_size

    def __float__(self) -> float:
        return self.value


class Timeframe(str, Enum):
    """A bar timeframe. Extend this enum, don't parameterize it with an
    arbitrary string - keeping it closed is what lets duration_minutes stay a
    simple, exhaustive lookup instead of a parser."""

    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    H1 = "1h"

    @property
    def duration_minutes(self) -> int:
        return _TIMEFRAME_MINUTES[self]


_TIMEFRAME_MINUTES: dict[Timeframe, int] = {
    Timeframe.M1: 1,
    Timeframe.M5: 5,
    Timeframe.M15: 15,
    Timeframe.H1: 60,
}


class Session(str, Enum):
    """Session IDENTITY only - which named session an event belongs to. Boundary
    computation (exact open/close clock times, holiday/DST handling) belongs to
    atlas.market_engine, not here - see this module's docstring."""

    RTH = "RTH"
    OVERNIGHT = "OVERNIGHT"
    NY = "NY"
    LONDON = "LONDON"
