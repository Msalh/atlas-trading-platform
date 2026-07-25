"""Explicit, immutable configuration for the private capture service."""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlsplit

from .errors import CaptureFailure, CaptureFailureCode


@dataclass(frozen=True, slots=True)
class ApprovedCaptureIdentity:
    product: str = "MNQ"
    timeframe: str = "5m"
    strategy_id: str = "displacement_volume_context"
    market_data_provider: str = "tradingview"
    market_data_series_symbol: str = "MNQ1!"
    market_data_series_type: str = "continuous"
    market_data_resolution_version: str = "tradingview-mnq1.v1"


@dataclass(frozen=True, slots=True)
class CaptureServiceConfig:
    """Secrets remain opaque and are excluded from repr."""

    trader_now_base_url: str = field(repr=False)
    trader_now_api_key: str = field(repr=False)
    enabled: bool = False
    request_timeout_seconds: float = 5.0
    approved_identity: ApprovedCaptureIdentity = ApprovedCaptureIdentity()

    def validate(self) -> None:
        parsed = urlsplit(self.trader_now_base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise CaptureFailure(CaptureFailureCode.CONFIGURATION)
        if not self.trader_now_api_key.strip():
            raise CaptureFailure(CaptureFailureCode.CONFIGURATION)
        if not 0 < self.request_timeout_seconds <= 30:
            raise CaptureFailure(CaptureFailureCode.CONFIGURATION)
