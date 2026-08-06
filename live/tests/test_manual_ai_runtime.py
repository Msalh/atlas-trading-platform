"""Offline qualification for the default-disabled manual OpenAI composition."""

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar

import pytest
import httpx

from atlas.config import Settings
from atlas.manual_ai_advisory import ManualAIExplanationService
from atlas.manual_ai_runtime import (
    MAX_ESTIMATED_COST_USD,
    MAX_INPUT_TOKENS,
    MAX_OUTPUT_TOKENS,
    MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES,
    MODEL_ID,
    PRICING_REFERENCE_ID,
    ManualAIProviderConfig,
    _estimate_input_tokens,
    _RuntimeCostPolicy,
    build_manual_ai_explanation_service,
)
from atlas_ai_analysis import GeneratorIdentity
from atlas_ai_orchestration import TrustedProviderRequest
from atlas_ai_orchestration.openai_adapter import OpenAIProviderAdapter

ROOT = Path(__file__).resolve().parents[1]

NOW = datetime(2026, 8, 6, 12, tzinfo=timezone.utc)
SECRET = "offline-runtime-secret-that-must-not-leak"


def _settings(**changes):
    values = {
        "environment": "development",
        "atlas_ai_provider_enabled": "true",
        "atlas_ai_provider_api_key": SECRET,
        "atlas_ai_provider_model": MODEL_ID,
        "atlas_ai_provider_timeout_seconds": "60",
        "atlas_ai_provider_max_request_bytes": str(MAX_REQUEST_BYTES),
        "atlas_ai_provider_max_response_bytes": str(MAX_RESPONSE_BYTES),
        "atlas_ai_provider_max_output_tokens": str(MAX_OUTPUT_TOKENS),
        "atlas_ai_provider_max_estimated_cost": str(MAX_ESTIMATED_COST_USD),
    }
    values.update(changes)
    return SimpleNamespace(**values)


class CapturingAdapter:
    instances: ClassVar[list["CapturingAdapter"]] = []

    def __init__(self, *, credential_provider, input_token_estimator, policy, **kwargs):
        self.credential_provider = credential_provider
        self.input_token_estimator = input_token_estimator
        self.policy = policy
        self.kwargs = kwargs
        self.calls = 0
        self.instances.append(self)

    @property
    def identity(self):
        return GeneratorIdentity("openai", self.policy.model_id)

    def invoke(self, _request):
        self.calls += 1
        raise AssertionError("startup must not invoke the provider")


@pytest.fixture(autouse=True)
def clear_adapters():
    CapturingAdapter.instances.clear()


@pytest.mark.parametrize("enabled", ["", "false", "TRUE", " true", "true ", "1"])
def test_disabled_or_malformed_enablement_constructs_no_provider(enabled):
    result = build_manual_ai_explanation_service(
        _settings(atlas_ai_provider_enabled=enabled),
        adapter_factory=CapturingAdapter,
        clock=lambda: NOW,
    )

    assert result is None
    assert CapturingAdapter.instances == []


def test_settings_disabled_mode_never_reads_provider_api_key(monkeypatch):
    names = []

    def read(name, default=None):
        names.append(name)
        if name == "ATLAS_AI_PROVIDER_ENABLED":
            return "false"
        if name == "ATLAS_AI_PROVIDER_API_KEY":
            raise AssertionError("disabled mode must not read the credential")
        return default

    monkeypatch.setattr("atlas.config.os.environ.get", read)
    configured = Settings()

    assert configured.atlas_ai_provider_enabled == "false"
    assert configured.atlas_ai_provider_api_key == ""
    assert "ATLAS_AI_PROVIDER_API_KEY" not in names


@pytest.mark.parametrize("enabled", ["TRUE", " true", "true ", "1"])
def test_settings_malformed_enablement_never_reads_provider_api_key(
    monkeypatch, enabled
):
    names = []

    def read(name, default=None):
        names.append(name)
        if name == "ENVIRONMENT":
            return "development"
        if name == "ATLAS_AI_PROVIDER_ENABLED":
            return enabled
        if name == "ATLAS_AI_PROVIDER_API_KEY":
            raise AssertionError("malformed mode must not read the credential")
        return default

    monkeypatch.setattr("atlas.config.os.environ.get", read)
    configured = Settings()

    assert configured.atlas_ai_provider_api_key == ""
    assert "ATLAS_AI_PROVIDER_API_KEY" not in names


def test_production_mode_never_reads_or_constructs_provider(monkeypatch):
    names = []

    def read(name, default=None):
        names.append(name)
        if name == "ENVIRONMENT":
            return "production"
        if name == "ATLAS_AI_PROVIDER_ENABLED":
            return "true"
        if name == "ATLAS_AI_PROVIDER_API_KEY":
            raise AssertionError("production mode must not read the local credential")
        return default

    monkeypatch.setattr("atlas.config.os.environ.get", read)
    configured = Settings()
    result = build_manual_ai_explanation_service(
        configured, adapter_factory=CapturingAdapter, clock=lambda: NOW
    )

    assert configured.atlas_ai_provider_api_key == ""
    assert "ATLAS_AI_PROVIDER_API_KEY" not in names
    assert result is None
    assert CapturingAdapter.instances == []


@pytest.mark.parametrize(
    "environment", ["Development", "DEVELOPMENT", " development", "development "]
)
def test_nonexact_development_environment_never_reads_or_constructs_provider(
    monkeypatch, environment
):
    names = []

    def read(name, default=None):
        names.append(name)
        if name == "ENVIRONMENT":
            return environment
        if name == "ATLAS_AI_PROVIDER_ENABLED":
            return "true"
        if name == "ATLAS_AI_PROVIDER_API_KEY":
            raise AssertionError("nonexact environment must not read the credential")
        return default

    monkeypatch.setattr("atlas.config.os.environ.get", read)
    configured = Settings()
    result = build_manual_ai_explanation_service(
        configured, adapter_factory=CapturingAdapter, clock=lambda: NOW
    )

    assert configured.atlas_ai_provider_api_key == ""
    assert "ATLAS_AI_PROVIDER_API_KEY" not in names
    assert result is None
    assert CapturingAdapter.instances == []


def test_enabled_configuration_constructs_one_exact_manual_service_without_invocation():
    config = ManualAIProviderConfig.from_settings(_settings())
    service = build_manual_ai_explanation_service(
        _settings(), adapter_factory=CapturingAdapter, clock=lambda: NOW
    )

    assert config is not None
    assert SECRET not in repr(config)
    assert type(service) is ManualAIExplanationService
    assert len(CapturingAdapter.instances) == 1
    adapter = CapturingAdapter.instances[0]
    assert adapter.calls == 0
    assert adapter.policy.enabled is True
    assert adapter.policy.model_id == MODEL_ID
    assert adapter.policy.approved_model_ids == frozenset({MODEL_ID})
    assert adapter.policy.pricing_reference_id == PRICING_REFERENCE_ID
    assert adapter.policy.max_request_bytes == MAX_REQUEST_BYTES
    assert adapter.policy.max_response_bytes == MAX_RESPONSE_BYTES
    assert adapter.policy.max_output_tokens == MAX_OUTPUT_TOKENS
    assert adapter.policy.max_estimated_cost_usd == float(MAX_ESTIMATED_COST_USD)
    assert adapter.kwargs["utc_now"]() == NOW
    assert SECRET not in repr(service)
    assert SECRET not in repr(adapter)
    assert SECRET not in repr(adapter.policy)


def test_each_runtime_service_owns_fresh_nonpersistent_diagnostics():
    first = build_manual_ai_explanation_service(
        _settings(), adapter_factory=CapturingAdapter, clock=lambda: NOW
    )
    second = build_manual_ai_explanation_service(
        _settings(), adapter_factory=CapturingAdapter, clock=lambda: NOW
    )

    first_diagnostics = first._provider_orchestrator._failure_diagnostics
    second_diagnostics = second._provider_orchestrator._failure_diagnostics
    assert first_diagnostics is not second_diagnostics
    assert sum(first_diagnostics.snapshot().values()) == 0
    assert sum(second_diagnostics.snapshot().values()) == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"atlas_ai_provider_api_key": ""},
        {"atlas_ai_provider_model": "other-model"},
        {"atlas_ai_provider_timeout_seconds": ""},
        {"atlas_ai_provider_timeout_seconds": " 60"},
        {"atlas_ai_provider_timeout_seconds": "6e1"},
        {"atlas_ai_provider_timeout_seconds": "61"},
        {"atlas_ai_provider_max_request_bytes": "0"},
        {"atlas_ai_provider_max_request_bytes": "065536"},
        {"atlas_ai_provider_max_request_bytes": str(MAX_REQUEST_BYTES + 1)},
        {"atlas_ai_provider_max_response_bytes": "not-an-integer"},
        {"atlas_ai_provider_max_output_tokens": str(MAX_OUTPUT_TOKENS + 1)},
        {"atlas_ai_provider_max_estimated_cost": "nan"},
        {"atlas_ai_provider_max_estimated_cost": "0.081919"},
        {"atlas_ai_provider_max_estimated_cost": "0.120001"},
    ],
)
def test_missing_unknown_or_out_of_policy_configuration_fails_before_construction(
    changes,
):
    result = build_manual_ai_explanation_service(
        _settings(**changes), adapter_factory=CapturingAdapter, clock=lambda: NOW
    )

    assert result is None
    assert CapturingAdapter.instances == []


@pytest.mark.parametrize("ceiling", ["0.081920", "0.12"])
def test_exact_cost_boundaries_are_accepted(ceiling):
    result = build_manual_ai_explanation_service(
        _settings(atlas_ai_provider_max_estimated_cost=ceiling),
        adapter_factory=CapturingAdapter,
        clock=lambda: NOW,
    )

    assert type(result) is ManualAIExplanationService
    assert len(CapturingAdapter.instances) == 1


def test_input_accounting_uses_utf8_bytes_and_rejects_over_token_ceiling():
    request = TrustedProviderRequest(
        schema_version="trusted_provider_request.v1",
        output_schema_version="ai_analysis_output.v1",
        analysis_output_id="output",
        analysis_input_id="input",
        snapshot_id="snapshot",
        evidence_digest="digest",
        purpose="strategy_explanation",
        trusted_instructions=("trusted",),
        untrusted_evidence_json="é" * (MAX_INPUT_TOKENS // 2),
    )

    estimate = _estimate_input_tokens(request)

    assert estimate > MAX_INPUT_TOKENS
    assert estimate > len(request.untrusted_evidence_json)
    assert _RuntimeCostPolicy().allows(request) is False


def test_expired_or_unavailable_pricing_fails_before_provider_construction(monkeypatch):
    expired = build_manual_ai_explanation_service(
        _settings(),
        adapter_factory=CapturingAdapter,
        clock=lambda: datetime(2026, 9, 5, tzinfo=timezone.utc),
    )
    assert expired is None
    assert CapturingAdapter.instances == []

    monkeypatch.setattr(
        "atlas.manual_ai_runtime.resolve_authoritative_pricing", lambda **_kwargs: None
    )
    unavailable = build_manual_ai_explanation_service(
        _settings(), adapter_factory=CapturingAdapter, clock=lambda: NOW
    )
    assert unavailable is None
    assert CapturingAdapter.instances == []


def test_factory_sanitizes_internal_rejection_without_secret_retention():
    class RejectingAdapter:
        def __init__(self, **_kwargs):
            raise RuntimeError(SECRET)

    result = build_manual_ai_explanation_service(
        _settings(), adapter_factory=RejectingAdapter, clock=lambda: NOW
    )

    assert result is None
    assert SECRET not in repr(result)


def test_invocation_time_pricing_expiry_precedes_credential_and_transport_access():
    clock = [NOW]
    credential_calls = 0
    transport_calls = 0

    def adapter_factory(**kwargs):
        original_credential_provider = kwargs.pop("credential_provider")

        def credential_provider():
            nonlocal credential_calls
            credential_calls += 1
            return original_credential_provider()

        def transport(_request):
            nonlocal transport_calls
            transport_calls += 1
            raise AssertionError("expired pricing must prevent transport")

        return OpenAIProviderAdapter(
            **kwargs,
            credential_provider=credential_provider,
            qualification_transport=httpx.MockTransport(transport),
        )

    service = build_manual_ai_explanation_service(
        _settings(), adapter_factory=adapter_factory, clock=lambda: clock[0]
    )
    assert type(service) is ManualAIExplanationService

    clock[0] = datetime(2026, 9, 5, tzinfo=timezone.utc)
    snapshot = json.loads(
        (
            ROOT
            / "specs"
            / "trader_now_snapshot"
            / "v1"
            / "golden"
            / "complete-current-candidate.canonical.json"
        ).read_text(encoding="utf-8")
    )
    source = {
        "schema_version": "trader_now_response.v2",
        "domain_schema_version": "trader_now.v2",
        **snapshot["evidence"],
    }

    result = service.explain(source)

    assert result.status == "unavailable"
    assert result.reason == "analysis_unavailable"
    assert credential_calls == 0
    assert transport_calls == 0
    assert SECRET not in repr(result)
