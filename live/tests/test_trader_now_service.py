"""Identity-validation tests for the composition-free Part 1 service."""

import pytest

from atlas.trader_now.errors import UnsupportedTraderNowIdentityError
from atlas.trader_now.service import TraderNowService


def test_service_accepts_only_the_approved_identity():
    identity = TraderNowService().validate_request(
        symbol="MNQ",
        timeframe="5m",
        strategy_id="displacement_volume_context",
    )
    assert identity.product == "MNQ"
    assert identity.symbol == "MNQ"
    assert identity.timeframe == "5m"
    assert identity.strategy_id == "displacement_volume_context"
    assert identity.strategy_version == "1.0.0"


@pytest.mark.parametrize(
    ("field", "request_values"),
    [
        (
            "symbol",
            {
                "symbol": "ES",
                "timeframe": "5m",
                "strategy_id": "displacement_volume_context",
            },
        ),
        (
            "symbol",
            {
                "symbol": "mnq",
                "timeframe": "5m",
                "strategy_id": "displacement_volume_context",
            },
        ),
        (
            "symbol",
            {
                "symbol": " MNQ ",
                "timeframe": "5m",
                "strategy_id": "displacement_volume_context",
            },
        ),
        (
            "timeframe",
            {
                "symbol": "MNQ",
                "timeframe": "1m",
                "strategy_id": "displacement_volume_context",
            },
        ),
        ("strategy_id", {"symbol": "MNQ", "timeframe": "5m", "strategy_id": "other"}),
    ],
)
def test_service_rejects_unsupported_values_without_normalization_or_fallback(
    field, request_values
):
    with pytest.raises(UnsupportedTraderNowIdentityError) as exc_info:
        TraderNowService().validate_request(**request_values)
    assert exc_info.value.field == field


def test_identity_error_reports_supplied_and_supported_values():
    with pytest.raises(UnsupportedTraderNowIdentityError) as exc_info:
        TraderNowService().validate_request(
            symbol="MNQ",
            timeframe="15m",
            strategy_id="displacement_volume_context",
        )
    assert exc_info.value.supplied == "15m"
    assert exc_info.value.supported == "5m"
