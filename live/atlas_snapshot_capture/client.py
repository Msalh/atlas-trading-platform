"""Authenticated HTTP adapter for the private TraderNow transport."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from .config import CaptureServiceConfig
from .errors import CaptureFailureCode, TraderNowClientFailure
from .models import CaptureRequest


class HttpTraderNowClient:
    """Calls exactly the approved read-only TraderNow endpoint."""

    def __init__(
        self,
        config: CaptureServiceConfig,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._config = config
        self._client = client
        self._owns_client = client is None

    async def start(self) -> None:
        self._config.validate()
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._config.trader_now_base_url.rstrip("/"),
                timeout=self._config.request_timeout_seconds,
                follow_redirects=False,
            )

    async def close(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def fetch_latest(
        self,
        request: CaptureRequest,
        *,
        correlation_id: str,
    ) -> Mapping[str, Any]:
        if self._client is None:
            raise TraderNowClientFailure(CaptureFailureCode.CONFIGURATION)
        try:
            response = await self._client.get(
                "/api/v1/trader-now",
                params={
                    "symbol": request.symbol,
                    "timeframe": request.timeframe,
                    "strategy_id": request.strategy_id,
                },
                headers={
                    "Authorization": f"Bearer {self._config.trader_now_api_key}",
                    "X-Correlation-ID": correlation_id,
                    "Accept": "application/json",
                },
            )
        except httpx.TimeoutException as error:
            raise TraderNowClientFailure(
                CaptureFailureCode.TRADER_NOW_TIMEOUT
            ) from error
        except httpx.RequestError as error:
            raise TraderNowClientFailure(
                CaptureFailureCode.TRADER_NOW_NETWORK
            ) from error
        if response.status_code == 401:
            raise TraderNowClientFailure(
                CaptureFailureCode.TRADER_NOW_AUTHENTICATION
            )
        if response.status_code == 403:
            raise TraderNowClientFailure(
                CaptureFailureCode.TRADER_NOW_AUTHORIZATION
            )
        if response.status_code != 200:
            raise TraderNowClientFailure(CaptureFailureCode.TRADER_NOW_RESPONSE)
        try:
            payload = response.json()
        except ValueError as error:
            raise TraderNowClientFailure(
                CaptureFailureCode.TRADER_NOW_RESPONSE
            ) from error
        if not isinstance(payload, dict):
            raise TraderNowClientFailure(CaptureFailureCode.TRADER_NOW_RESPONSE)
        return payload
