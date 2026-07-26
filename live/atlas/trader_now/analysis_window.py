"""TraderNow analysis-window selection using canonical replay segmentation."""

from dataclasses import replace

from atlas.replay_engine.segmentation import segment_replay_window
from atlas.trader_now.models import (
    AvailabilityStatus,
    MarketInputWindow,
)


def latest_contiguous_analysis_window(
    market_input: MarketInputWindow,
) -> MarketInputWindow:
    """Return the latest exact-cadence segment without changing source identity."""
    if (
        market_input.availability.status != AvailabilityStatus.AVAILABLE
        or market_input.identity is None
        or not market_input.states
    ):
        return market_input

    segments = segment_replay_window(list(market_input.states))
    return replace(market_input, states=tuple(segments[-1]))
