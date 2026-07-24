"""The single explicitly-approved TraderNow product identity."""

from atlas.trader_now.errors import UnsupportedTraderNowIdentityError
from atlas.trader_now.models import TraderNowIdentity

SUPPORTED_PRODUCT = "MNQ"
SUPPORTED_TIMEFRAME = "5m"
SUPPORTED_STRATEGY_ID = "displacement_volume_context"
SUPPORTED_STRATEGY_VERSION = "1.0.0"


def validate_identity(
    symbol: str, timeframe: str, strategy_id: str
) -> TraderNowIdentity:
    """Validate without normalization, aliases, or silent fallback."""
    supported = (
        ("symbol", symbol, SUPPORTED_PRODUCT),
        ("timeframe", timeframe, SUPPORTED_TIMEFRAME),
        ("strategy_id", strategy_id, SUPPORTED_STRATEGY_ID),
    )
    for field, supplied, expected in supported:
        if supplied != expected:
            raise UnsupportedTraderNowIdentityError(field, supplied, expected)

    return TraderNowIdentity(
        product=SUPPORTED_PRODUCT,
        symbol=symbol,
        timeframe=timeframe,
        strategy_id=strategy_id,
        strategy_version=SUPPORTED_STRATEGY_VERSION,
    )
