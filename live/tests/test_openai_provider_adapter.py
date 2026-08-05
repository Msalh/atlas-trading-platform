"""Offline Phase 18E qualification for the concrete OpenAI adapter."""

from __future__ import annotations

import json
from collections.abc import Callable
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
)

MODEL = "offline-approved-model-snapshot"
SECRET = "offline-secret-that-must-not-leak"
EVIDENCE_MARKER = "private-evidence-that-must-not-leak"


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
        "input_usd_per_million_tokens": 2.0,
        "output_usd_per_million_tokens": 12.0,
        "pricing_verified": True,
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
) -> tuple[OpenAIProviderAdapter, httpx.Client]:
    client = httpx.Client(transport=httpx.MockTransport(handler), trust_env=False)
    adapter = OpenAIProviderAdapter(
        client=client,
        credential_provider=credential,
        input_token_estimator=estimator,
        policy=policy or _policy(),
        **({"monotonic": monotonic} if monotonic else {}),
    )
    return adapter, client


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
        (_policy(pricing_verified=False), lambda _request: 1),
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
