"""Authenticated, exact-route TraderNow client contract tests."""

from __future__ import annotations

import httpx
import pytest

from atlas_snapshot_capture import (
    CaptureFailureCode,
    CaptureRequest,
    CaptureServiceConfig,
    HttpTraderNowClient,
    TraderNowClientFailure,
)

REQUEST = CaptureRequest("MNQ", "5m", "displacement_volume_context")


def _config():
    return CaptureServiceConfig(
        trader_now_base_url="https://private.example",
        trader_now_api_key="private-key",
        enabled=True,
        request_timeout_seconds=2,
    )


@pytest.mark.asyncio
async def test_exact_route_query_authentication_and_correlation_forwarding():
    observed = {}

    def handler(request):
        observed["request"] = request
        return httpx.Response(
            200,
            json={
                "schema_version": "trader_now_response.v2",
                "domain_schema_version": "trader_now.v2",
            },
        )

    async_client = httpx.AsyncClient(
        base_url="https://private.example",
        transport=httpx.MockTransport(handler),
    )
    client = HttpTraderNowClient(_config(), client=async_client)
    await client.start()

    await client.fetch_latest(REQUEST, correlation_id="corr-123")

    request = observed["request"]
    assert request.url.path == "/api/v1/trader-now"
    assert dict(request.url.params) == {
        "symbol": "MNQ",
        "timeframe": "5m",
        "strategy_id": "displacement_volume_context",
    }
    assert request.headers["Authorization"] == "Bearer private-key"
    assert request.headers["X-Correlation-ID"] == "corr-123"
    await client.close()
    assert async_client.is_closed is False
    await async_client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "code"),
    [
        (401, CaptureFailureCode.TRADER_NOW_AUTHENTICATION),
        (403, CaptureFailureCode.TRADER_NOW_AUTHORIZATION),
        (500, CaptureFailureCode.TRADER_NOW_RESPONSE),
    ],
)
async def test_http_status_failures_are_stable_and_sanitized(status, code):
    transport = httpx.MockTransport(lambda _request: httpx.Response(status))
    async with httpx.AsyncClient(
        base_url="https://private.example", transport=transport
    ) as async_client:
        client = HttpTraderNowClient(_config(), client=async_client)
        await client.start()
        with pytest.raises(TraderNowClientFailure) as failure:
            await client.fetch_latest(REQUEST, correlation_id="corr")
        assert failure.value.code is code
        assert "private-key" not in str(failure.value)


@pytest.mark.asyncio
async def test_timeout_network_and_malformed_json_are_typed():
    cases = [
        (
            httpx.MockTransport(
                lambda request: (_ for _ in ()).throw(
                    httpx.ReadTimeout("secret URL", request=request)
                )
            ),
            CaptureFailureCode.TRADER_NOW_TIMEOUT,
        ),
        (
            httpx.MockTransport(
                lambda request: (_ for _ in ()).throw(
                    httpx.ConnectError("secret host", request=request)
                )
            ),
            CaptureFailureCode.TRADER_NOW_NETWORK,
        ),
        (
            httpx.MockTransport(
                lambda _request: httpx.Response(
                    200,
                    content=b"not-json",
                    headers={"content-type": "application/json"},
                )
            ),
            CaptureFailureCode.TRADER_NOW_RESPONSE,
        ),
    ]
    for transport, expected in cases:
        async with httpx.AsyncClient(
            base_url="https://private.example", transport=transport
        ) as async_client:
            client = HttpTraderNowClient(_config(), client=async_client)
            await client.start()
            with pytest.raises(TraderNowClientFailure) as failure:
                await client.fetch_latest(REQUEST, correlation_id="corr")
            assert failure.value.code is expected


def test_configuration_rejects_embedded_credentials_and_redacts_api_key():
    config = CaptureServiceConfig(
        trader_now_base_url="https://user:password@private.example",
        trader_now_api_key="secret-value",
    )
    with pytest.raises(Exception) as failure:
        config.validate()
    assert "secret-value" not in repr(config)
    assert "private.example" not in repr(config)
    assert "password" not in str(failure.value)
