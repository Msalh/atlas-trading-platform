"""Offline Phase 18E qualification for the concrete OpenAI adapter."""

from __future__ import annotations

import json
import inspect
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import pytest

from atlas_ai_orchestration import TrustedProviderRequest
from atlas_ai_orchestration.errors import (
    ProviderPortError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from atlas_ai_orchestration.openai_adapter import (
    OpenAIAdapterPolicy,
    OpenAIProviderAdapter,
    ProviderPricingRecord,
)

MODEL = "offline-approved-model-snapshot"
SECRET = "offline-secret-that-must-not-leak"
EVIDENCE_MARKER = "private-evidence-that-must-not-leak"
NOW = datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc)


def _pricing(**changes: Any) -> ProviderPricingRecord:
    values = {
        "provider_id": "openai",
        "model_id": MODEL,
        "input_usd_per_million_tokens": 2.0,
        "output_usd_per_million_tokens": 12.0,
        "currency": "USD",
        "unit": "per_million_tokens",
        "service_tier": "default",
        "source_id": "official-openai-pricing",
        "source_version": "2026-07-30",
        "effective_at": NOW - timedelta(days=6),
        "verified_at": NOW - timedelta(hours=1),
        "expires_at": NOW + timedelta(days=1),
        "maximum_age_seconds": 86_400,
    }
    values.update(changes)
    return ProviderPricingRecord(**values)


def _traceback_locals(error: BaseException) -> str:
    values: list[str] = []
    traceback = error.__traceback__
    while traceback is not None:
        values.extend(repr(value) for value in traceback.tb_frame.f_locals.values())
        traceback = traceback.tb_next
    return "\n".join(values)


def _request(evidence: str = "{}") -> TrustedProviderRequest:
    return TrustedProviderRequest(
        schema_version="trusted_provider_request.v1",
        output_schema_version="ai_analysis_output.v1",
        analysis_output_id="019c1234-0000-7000-8000-000000000002",
        analysis_input_id="019c1234-0000-7000-8000-000000000001",
        snapshot_id="019849d1-8c00-7000-8000-000000000004",
        evidence_digest="5" * 64,
        purpose="strategy_explanation",
        trusted_instructions=("trusted",),
        untrusted_evidence_json=evidence,
    )


def _policy(**changes: Any) -> OpenAIAdapterPolicy:
    pricing = changes.pop("pricing", _pricing())
    values = {
        "enabled": True,
        "model_id": MODEL,
        "approved_model_ids": frozenset({MODEL}),
        "pricing": pricing,
        "approved_pricing_records": (pricing,),
        "approved_pricing_sources": frozenset(
            {("official-openai-pricing", "2026-07-30")}
        ),
    }
    values.update(changes)
    return OpenAIAdapterPolicy(**values)


def _provider_body(candidate: Any) -> bytes:
    text = json.dumps(candidate, ensure_ascii=False, separators=(",", ":"))
    return json.dumps(
        {
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": text}],
                }
            ]
        },
        separators=(",", ":"),
    ).encode()


def _adapter(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    policy: OpenAIAdapterPolicy | None = None,
    credential: Callable[[], str] = lambda: SECRET,
    estimator: Callable[[TrustedProviderRequest], int] = lambda _request: 100,
    monotonic: Callable[[], float] | None = None,
) -> tuple[OpenAIProviderAdapter, httpx.MockTransport]:
    transport = httpx.MockTransport(handler)
    adapter = OpenAIProviderAdapter(
        credential_provider=credential,
        input_token_estimator=estimator,
        policy=policy or _policy(),
        qualification_transport=transport,
        utc_now=lambda: NOW,
        **({"monotonic": monotonic} if monotonic else {}),
    )
    return adapter, transport


@pytest.mark.parametrize(
    "candidate",
    [
        {"schema_version": "invalid-but-unchanged"},
        [1, {"nested": True}],
        "scalar",
        7,
        1.25,
        True,
        None,
    ],
)
def test_decoded_json_domain_candidate_is_returned_unchanged(candidate):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        assert request.headers["authorization"] == f"Bearer {SECRET}"
        payload = json.loads(request.content)
        assert payload["model"] == MODEL
        assert payload["store"] is False
        assert payload["stream"] is False
        assert payload["service_tier"] == "default"
        assert payload["prompt_cache_options"] == {"mode": "explicit"}
        assert payload["max_output_tokens"] == 4096
        provider_input = json.loads(payload["input"])
        assert provider_input["analysis_output_id"] == _request().analysis_output_id
        assert provider_input["untrusted_evidence_json"] == "{}"
        return httpx.Response(200, content=_provider_body(candidate))

    adapter, client = _adapter(handler)
    try:
        result = adapter.invoke(_request())
    finally:
        client.close()

    assert result == candidate
    assert type(result) is type(candidate)
    assert calls == 1


def test_counted_transport_symbol_runs_exactly_once(monkeypatch):
    adapter, client = _adapter(
        lambda _request: httpx.Response(200, content=_provider_body({"ok": True}))
    )
    calls = 0
    original = httpx.Client.send

    def counted(self, request, **kwargs):
        nonlocal calls
        calls += 1
        assert kwargs == {"stream": True, "follow_redirects": False}
        return original(self, request, **kwargs)

    monkeypatch.setattr(httpx.Client, "send", counted)
    try:
        assert adapter.invoke(_request()) == {"ok": True}
    finally:
        client.close()
    assert calls == 1


@pytest.mark.parametrize(
    ("policy", "estimator"),
    [
        (_policy(enabled=False), lambda _request: 1),
        (_policy(model_id="not-allowlisted"), lambda _request: 1),
        (_policy(approved_model_ids=MODEL), lambda _request: 1),
        (_policy(pricing=None, approved_pricing_records=()), lambda _request: 1),
        (_policy(max_request_bytes=65_537), lambda _request: 1),
        (_policy(max_response_bytes=131_073), lambda _request: 1),
        (_policy(max_input_tokens=16_385), lambda _request: 1),
        (_policy(max_output_tokens=4_097), lambda _request: 1),
        (_policy(connect_timeout_seconds=5.01), lambda _request: 1),
        (_policy(read_timeout_seconds=45.01), lambda _request: 1),
        (_policy(deadline_seconds=60.01), lambda _request: 1),
        (_policy(max_estimated_cost_usd=0.1201), lambda _request: 1),
        (_policy(), lambda _request: 16_385),
    ],
)
def test_invalid_policy_or_input_limit_fails_before_credential_and_transport(
    policy, estimator
):
    credential_calls = 0
    transport_calls = 0

    def credential():
        nonlocal credential_calls
        credential_calls += 1
        return SECRET

    def handler(_request):
        nonlocal transport_calls
        transport_calls += 1
        raise AssertionError

    adapter, client = _adapter(
        handler, policy=policy, credential=credential, estimator=estimator
    )
    try:
        with pytest.raises(ProviderPortError) as captured:
            adapter.invoke(_request())
    finally:
        client.close()
    assert credential_calls == transport_calls == 0
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None


def test_estimated_cost_over_ceiling_fails_before_transport():
    adapter, client = _adapter(
        lambda _request: pytest.fail("transport must not run"),
        policy=_policy(max_estimated_cost_usd=0.08),
        estimator=lambda _request: 16_384,
    )
    try:
        with pytest.raises(ProviderPortError):
            adapter.invoke(_request())
    finally:
        client.close()


def test_oversized_serialized_request_fails_before_transport():
    adapter, client = _adapter(
        lambda _request: pytest.fail("transport must not run"),
        policy=_policy(max_request_bytes=512),
    )
    try:
        with pytest.raises(ProviderPortError):
            adapter.invoke(_request("x" * 1_000))
    finally:
        client.close()


@pytest.mark.parametrize(
    ("status", "error_type"),
    [
        (400, ProviderPortError),
        (401, ProviderPortError),
        (403, ProviderPortError),
        (408, ProviderUnavailableError),
        (429, ProviderUnavailableError),
        (500, ProviderUnavailableError),
    ],
)
def test_http_failure_is_sanitized(status, error_type):
    adapter, client = _adapter(lambda _request: httpx.Response(status, text=SECRET))
    try:
        with pytest.raises(error_type) as captured:
            adapter.invoke(_request())
    finally:
        client.close()
    assert str(captured.value) == ""
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None
    assert SECRET not in repr(captured.value)


@pytest.mark.parametrize(
    ("raised", "error_type"),
    [
        (httpx.ReadTimeout(SECRET), ProviderTimeoutError),
        (httpx.ConnectError(SECRET), ProviderUnavailableError),
        (RuntimeError(SECRET), ProviderPortError),
    ],
)
def test_hostile_transport_exception_is_sanitized(raised, error_type):
    def handler(_request):
        raise raised

    adapter, client = _adapter(handler)
    try:
        with pytest.raises(error_type) as captured:
            adapter.invoke(_request())
    finally:
        client.close()
    assert str(captured.value) == ""
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None
    assert SECRET not in repr(captured.value)


def test_oversized_response_is_discarded_and_unavailable():
    adapter, client = _adapter(
        lambda _request: httpx.Response(200, content=b"x" * 1025),
        policy=_policy(max_response_bytes=1024),
    )
    try:
        with pytest.raises(ProviderUnavailableError):
            adapter.invoke(_request())
    finally:
        client.close()


def test_deadline_is_checked_while_streaming_and_after_transport():
    moments = iter((0.0, 61.0))
    adapter, client = _adapter(
        lambda _request: httpx.Response(200, content=_provider_body({"ok": True})),
        monotonic=lambda: next(moments),
    )
    try:
        with pytest.raises(ProviderTimeoutError):
            adapter.invoke(_request())
    finally:
        client.close()


@pytest.mark.parametrize(
    "content",
    [
        b"not-json-" + SECRET.encode(),
        json.dumps({"output": []}).encode(),
        json.dumps({"output": [{"type": "message", "content": []}]}).encode(),
        json.dumps(
            {
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "not-json"}],
                    }
                ]
            }
        ).encode(),
    ],
)
def test_missing_or_malformed_candidate_fails_without_raw_material(content):
    adapter, client = _adapter(lambda _request: httpx.Response(200, content=content))
    try:
        with pytest.raises(ProviderPortError) as captured:
            adapter.invoke(_request())
    finally:
        client.close()
    assert str(captured.value) == ""
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None
    assert SECRET not in repr(captured.value)


@pytest.mark.parametrize(
    "candidate_text",
    ["NaN", "Infinity", '{"duplicate":1,"duplicate":2}'],
)
def test_nonstandard_or_duplicate_key_json_is_rejected(candidate_text):
    response = json.dumps(
        {
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": candidate_text}],
                }
            ]
        }
    ).encode()
    adapter, client = _adapter(lambda _request: httpx.Response(200, content=response))
    try:
        with pytest.raises(ProviderPortError):
            adapter.invoke(_request())
    finally:
        client.close()


def test_absent_candidate_uses_unavailable_classification():
    adapter, client = _adapter(
        lambda _request: httpx.Response(200, json={"output": []})
    )
    try:
        with pytest.raises(ProviderUnavailableError):
            adapter.invoke(_request())
    finally:
        client.close()


def test_missing_credential_fails_closed_without_transport():
    adapter, client = _adapter(
        lambda _request: pytest.fail("transport must not run"), credential=lambda: ""
    )
    try:
        with pytest.raises(ProviderPortError) as captured:
            adapter.invoke(_request())
    finally:
        client.close()
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None


def test_sanitized_failure_traceback_does_not_retain_request_or_response_material():
    adapter, client = _adapter(
        lambda _request: httpx.Response(500, text=SECRET),
    )
    try:
        with pytest.raises(ProviderUnavailableError) as captured:
            adapter.invoke(_request(EVIDENCE_MARKER))
    finally:
        client.close()
    retained = _traceback_locals(captured.value)
    assert SECRET not in retained
    assert EVIDENCE_MARKER not in retained


class CountingTransport(httpx.BaseTransport):
    def __init__(self, response_factory):
        self.calls = 0
        self.response_factory = response_factory

    def handle_request(self, request):
        self.calls += 1
        return self.response_factory(request)


class HostileStream(httpx.SyncByteStream):
    def __init__(self, chunks=(), raised=None):
        self._chunks = chunks
        self._raised = raised

    def __iter__(self):
        if self._raised is not None:
            raise self._raised
        yield from self._chunks

    def close(self):
        raise RuntimeError(SECRET)


def _assert_clean(error: BaseException) -> None:
    assert str(error) == ""
    assert SECRET not in repr(error)
    assert error.__cause__ is None
    assert error.__context__ is None
    assert SECRET not in _traceback_locals(error)
    assert EVIDENCE_MARKER not in _traceback_locals(error)


def test_adapter_does_not_accept_client_auth_hooks_mounts_proxy_or_http2():
    parameters = inspect.signature(OpenAIProviderAdapter).parameters
    assert "client" not in parameters
    assert "auth" not in parameters
    assert "event_hooks" not in parameters
    assert "mounts" not in parameters
    assert "proxy" not in parameters
    assert "http2" not in parameters


def test_adapter_owned_client_configuration_is_fixed(monkeypatch):
    observed = {}
    original = httpx.Client

    def capturing_client(**kwargs):
        observed.update(kwargs)
        return original(**kwargs)

    monkeypatch.setattr(httpx, "Client", capturing_client)
    adapter, transport = _adapter(
        lambda _request: httpx.Response(200, content=_provider_body({"ok": True}))
    )
    assert adapter.invoke(_request()) == {"ok": True}
    assert observed["trust_env"] is False
    assert observed["http2"] is False
    assert observed["follow_redirects"] is False
    assert observed["auth"] is None
    assert observed["proxy"] is None
    assert observed["mounts"] is None
    assert observed["event_hooks"] == {"request": [], "response": []}
    assert observed["limits"].max_connections == 1
    assert observed["limits"].max_keepalive_connections == 0
    transport.close()


def test_production_transport_has_retries_disabled(monkeypatch):
    marker = httpx.MockTransport(lambda _request: httpx.Response(500))
    seen = []

    def transport_factory(**kwargs):
        seen.append(kwargs)
        return marker

    monkeypatch.setattr(httpx, "HTTPTransport", transport_factory)
    adapter = OpenAIProviderAdapter(
        credential_provider=lambda: SECRET,
        input_token_estimator=lambda _request: 1,
        policy=_policy(),
        utc_now=lambda: NOW,
    )
    assert adapter._transport() is marker
    assert seen == [{"retries": 0}]
    marker.close()


def test_one_send_is_one_transport_invocation_and_redirect_is_not_followed():
    transport = CountingTransport(lambda request: httpx.Response(302, headers={"location": str(request.url)}))
    adapter = OpenAIProviderAdapter(
        credential_provider=lambda: SECRET,
        input_token_estimator=lambda _request: 1,
        policy=_policy(),
        qualification_transport=transport,
        utc_now=lambda: NOW,
    )
    with pytest.raises(ProviderPortError):
        adapter.invoke(_request())
    assert transport.calls == 1


@pytest.mark.parametrize(
    "policy",
    [
        _policy(pricing=None, approved_pricing_records=()),
        _policy(pricing=_pricing(source_id="")),
        _policy(pricing=_pricing(source_version="")),
        _policy(pricing=_pricing(source_version="unapproved")),
        _policy(pricing=_pricing(provider_id="other")),
        _policy(pricing=_pricing(model_id="other")),
        _policy(pricing=_pricing(service_tier="priority")),
        _policy(pricing=_pricing(currency="EUR")),
        _policy(pricing=_pricing(unit="per_token")),
        _policy(pricing=_pricing(effective_at=NOW + timedelta(seconds=1))),
        _policy(pricing=_pricing(verified_at=NOW - timedelta(days=2))),
        _policy(pricing=_pricing(expires_at=NOW)),
        _policy(
            pricing=_pricing(input_usd_per_million_tokens=0.01),
            approved_pricing_records=(_pricing(),),
        ),
        _policy(approved_pricing_records=(_pricing(), _pricing())),
        _policy(pricing=_pricing(output_usd_per_million_tokens=22.0)),
    ],
)
def test_invalid_or_untrusted_pricing_fails_before_transport(policy):
    calls = 0

    def handler(_request):
        nonlocal calls
        calls += 1
        raise AssertionError

    adapter, transport = _adapter(handler, policy=policy)
    with pytest.raises(ProviderPortError):
        adapter.invoke(_request())
    assert calls == 0
    transport.close()


def test_pricing_ceiling_boundary_and_just_over_boundary():
    boundary_rate = (120_000 - 16_384 * 2.0) / 4_096
    accepted = _pricing(output_usd_per_million_tokens=boundary_rate)
    adapter, transport = _adapter(
        lambda _request: httpx.Response(200, content=_provider_body({"ok": True})),
        policy=_policy(pricing=accepted, approved_pricing_records=(accepted,)),
    )
    assert adapter.invoke(_request()) == {"ok": True}
    transport.close()
    over = replace(accepted, output_usd_per_million_tokens=boundary_rate + 0.000001)
    adapter, transport = _adapter(
        lambda _request: pytest.fail("transport must not run"),
        policy=_policy(pricing=over, approved_pricing_records=(over,)),
    )
    with pytest.raises(ProviderPortError):
        adapter.invoke(_request())
    transport.close()


@pytest.mark.parametrize(
    ("status", "stream", "expected"),
    [
        (200, HostileStream([_provider_body({"ok": True})]), ProviderPortError),
        (500, HostileStream([b"ignored"]), ProviderUnavailableError),
        (200, HostileStream([b"malformed"]), ProviderPortError),
        (200, HostileStream([b"x" * 2_000]), ProviderUnavailableError),
        (200, HostileStream(raised=httpx.ReadTimeout(SECRET)), ProviderTimeoutError),
    ],
)
def test_hostile_response_close_is_sanitized_and_preserves_selected_failure(
    status, stream, expected
):
    adapter, transport = _adapter(
        lambda request: httpx.Response(status, stream=stream, request=request),
        policy=_policy(max_response_bytes=1024),
    )
    with pytest.raises(expected) as captured:
        adapter.invoke(_request(EVIDENCE_MARKER))
    _assert_clean(captured.value)
    transport.close()
