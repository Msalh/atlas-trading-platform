"""Offline Phase 18E qualification for the concrete OpenAI adapter."""

from __future__ import annotations

import inspect
import json
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import pytest
from atlas_ai_orchestration import TrustedProviderRequest
from atlas_ai_orchestration import openai_adapter as adapter_module
from atlas_ai_orchestration.errors import (
    ProviderPortError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from atlas_ai_orchestration.openai_adapter import (
    OpenAIAdapterPolicy,
    OpenAIProviderAdapter,
)
from atlas_ai_orchestration.pricing_authority import (
    ProviderPricingRecord,
    _catalog_digest,
    _resolve_catalog,
    resolve_authoritative_pricing,
)

MODEL = "offline-approved-model-snapshot"
SECRET = "offline-secret-that-must-not-leak"
EVIDENCE_MARKER = "private-evidence-that-must-not-leak"
NOW = datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc)
REFERENCE = "offline-approved-pricing-reference"
CATALOG_VERSION = "offline-qualification-catalog.v1"
APPROVED_SOURCE = ("official-openai-pricing", "2026-07-30")


def _pricing(**changes: Any) -> ProviderPricingRecord:
    values = {
        "reference_id": REFERENCE,
        "catalog_version": CATALOG_VERSION,
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


def _qualification_resolver(
    records: tuple[ProviderPricingRecord, ...],
    *,
    approved_sources: frozenset[tuple[str, str]] = frozenset({APPROVED_SOURCE}),
    catalog_version: str = CATALOG_VERSION,
    catalog_sha256: str | None = None,
):
    digest = catalog_sha256 or _catalog_digest(records)

    def resolve(*, provider_id, model_id, service_tier, reference_id, now):
        return _resolve_catalog(
            records=records,
            approved_sources=approved_sources,
            expected_catalog_version=catalog_version,
            expected_catalog_sha256=digest,
            provider_id=provider_id,
            model_id=model_id,
            service_tier=service_tier,
            reference_id=reference_id,
            now=now,
        )

    return resolve


@pytest.fixture(autouse=True)
def qualification_pricing_authority(monkeypatch):
    monkeypatch.setattr(
        adapter_module,
        "resolve_authoritative_pricing",
        _qualification_resolver((_pricing(),)),
    )


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
    values = {
        "enabled": True,
        "model_id": MODEL,
        "approved_model_ids": frozenset({MODEL}),
        "pricing_reference_id": REFERENCE,
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
        (_policy(pricing_reference_id=""), lambda _request: 1),
        (_policy(pricing_reference_id="unapproved-reference"), lambda _request: 1),
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
    "record_changes",
    [
        {"source_id": ""},
        {"source_version": "unapproved"},
        {"provider_id": "other"},
        {"model_id": "other"},
        {"service_tier": "priority"},
        {"currency": "EUR"},
        {"unit": "per_token"},
        {"effective_at": NOW + timedelta(seconds=1)},
        {"verified_at": NOW - timedelta(days=2)},
        {"expires_at": NOW},
    ],
)
def test_invalid_authoritative_pricing_fails_before_any_caller_or_transport(
    monkeypatch, record_changes
):
    record = _pricing(**record_changes)
    monkeypatch.setattr(
        adapter_module,
        "resolve_authoritative_pricing",
        _qualification_resolver((record,)),
    )
    _assert_pricing_rejected_before_side_effects(monkeypatch)


def _assert_pricing_rejected_before_side_effects(monkeypatch):
    calls = {"estimator": 0, "credential": 0, "client": 0, "send": 0, "transport": 0}

    def estimator(_request):
        calls["estimator"] += 1
        return 1

    def credential():
        calls["credential"] += 1
        return SECRET

    def client(_self):
        calls["client"] += 1
        raise AssertionError

    def send(*args, **kwargs):
        calls["send"] += 1
        raise AssertionError

    def handler(_request):
        calls["transport"] += 1
        raise AssertionError

    monkeypatch.setattr(httpx.Client, "send", send)
    monkeypatch.setattr(OpenAIProviderAdapter, "_client", client)
    adapter, transport = _adapter(handler, credential=credential, estimator=estimator)
    with pytest.raises(ProviderPortError) as captured:
        adapter.invoke(_request(EVIDENCE_MARKER))
    _assert_clean(captured.value)
    assert calls == {"estimator": 0, "credential": 0, "client": 0, "send": 0, "transport": 0}
    transport.close()


def test_policy_caller_cannot_supply_or_redefine_pricing_authority(monkeypatch):
    parameters = inspect.signature(OpenAIAdapterPolicy).parameters
    prohibited = {
        "pricing",
        "rates",
        "approved_pricing_records",
        "approved_pricing_sources",
        "approved_source_versions",
        "pricing_catalog",
        "pricing_authority",
    }
    assert prohibited.isdisjoint(parameters)
    for name in prohibited:
        with pytest.raises(TypeError):
            _policy(**{name: object()})
    monkeypatch.setattr(
        adapter_module, "resolve_authoritative_pricing", resolve_authoritative_pricing
    )
    _assert_pricing_rejected_before_side_effects(monkeypatch)


def test_production_authority_cannot_use_offline_qualification_catalog(monkeypatch):
    monkeypatch.setattr(
        adapter_module, "resolve_authoritative_pricing", resolve_authoritative_pricing
    )
    _assert_pricing_rejected_before_side_effects(monkeypatch)


def test_catalog_integrity_duplicate_and_source_approval_fail_closed(monkeypatch):
    record = _pricing()
    resolvers = (
        _qualification_resolver((record,), catalog_sha256="0" * 64),
        _qualification_resolver((record, record)),
        _qualification_resolver((record, replace(record, model_id="conflict"))),
        _qualification_resolver((record,), approved_sources=frozenset()),
        _qualification_resolver((replace(record, catalog_version="other"),)),
    )
    for resolver in resolvers:
        monkeypatch.setattr(adapter_module, "resolve_authoritative_pricing", resolver)
        _assert_pricing_rejected_before_side_effects(monkeypatch)


def test_pricing_ceiling_boundary_and_just_over_boundary(monkeypatch):
    boundary_rate = (120_000 - 16_384 * 2.0) / 4_096
    accepted = _pricing(output_usd_per_million_tokens=boundary_rate)
    adapter, transport = _adapter(
        lambda _request: httpx.Response(200, content=_provider_body({"ok": True})),
        policy=_policy(),
    )
    monkeypatch.setattr(adapter_module, "resolve_authoritative_pricing", _qualification_resolver((accepted,)))
    assert adapter.invoke(_request()) == {"ok": True}
    transport.close()
    over = replace(accepted, output_usd_per_million_tokens=boundary_rate + 0.000001)
    adapter, transport = _adapter(
        lambda _request: pytest.fail("transport must not run"),
        policy=_policy(),
    )
    monkeypatch.setattr(adapter_module, "resolve_authoritative_pricing", _qualification_resolver((over,)))
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


def test_hostile_client_close_is_sanitized(monkeypatch):
    def hostile_close(_self):
        hostile_local = SECRET
        raise RuntimeError(hostile_local)

    monkeypatch.setattr(httpx.Client, "close", hostile_close)
    adapter, transport = _adapter(
        lambda _request: httpx.Response(200, content=_provider_body({"ok": True}))
    )
    with pytest.raises(ProviderPortError) as captured:
        adapter.invoke(_request(EVIDENCE_MARKER))
    _assert_clean(captured.value)
    transport.close()


def test_hostile_client_close_does_not_replace_selected_failure(monkeypatch):
    def hostile_close(_self):
        hostile_local = SECRET
        raise RuntimeError(hostile_local)

    monkeypatch.setattr(httpx.Client, "close", hostile_close)
    adapter, transport = _adapter(lambda _request: httpx.Response(500, text=SECRET))
    with pytest.raises(ProviderUnavailableError) as captured:
        adapter.invoke(_request(EVIDENCE_MARKER))
    _assert_clean(captured.value)
    transport.close()
