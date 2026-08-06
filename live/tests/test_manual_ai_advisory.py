"""Offline tests for the manual-only Phase 18 explanation composition."""

import json
from pathlib import Path

import pytest
from atlas.manual_ai_advisory import ManualAIExplanationService
from atlas_ai_analysis import GeneratorIdentity
from atlas_ai_orchestration import (
    DeterministicPromptBuilder,
    ProviderOrchestrator,
    ProviderTimeoutError,
)

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "specs" / "trader_now_snapshot" / "v1" / "golden"
IDS = iter(
    (
        "00000000-0000-7000-8000-000000000101",
        "00000000-0000-7000-8000-000000000102",
    )
)
NOW = "2026-08-06T12:00:00.000000Z"
GENERATOR = GeneratorIdentity("offline-provider", "offline-model")


class Provider:
    identity = GENERATOR

    def __init__(self, result):
        self.result = result
        self.calls = 0

    def invoke(self, request):
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        if callable(self.result):
            return self.result(request)
        return self.result


class AllowCost:
    def allows(self, _request):
        return True


def _source(name="complete-current-candidate.canonical.json"):
    snapshot = json.loads((GOLDEN / name).read_text(encoding="utf-8"))
    return {
        "schema_version": "trader_now_response.v2",
        "domain_schema_version": "trader_now.v2",
        **snapshot["evidence"],
    }


def _candidate(request):
    value = json.loads(
        (ROOT / "specs" / "ai_analysis" / "v1" / "golden" / "output.complete-current.json")
        .read_text(encoding="utf-8")
    )
    value.update(
        analysis_output_id=request.analysis_output_id,
        analysis_input_id=request.analysis_input_id,
        snapshot_id=request.snapshot_id,
        evidence_digest=request.evidence_digest,
        purpose=request.purpose,
    )
    return value


def _service(provider):
    ids = iter((
        "00000000-0000-7000-8000-000000000101",
        "00000000-0000-7000-8000-000000000102",
    ))
    orchestrator = ProviderOrchestrator(
        prompt_builder=DeterministicPromptBuilder(
            lambda: "00000000-0000-7000-8000-000000000103"
        ),
        provider=provider,
        cost_policy=AllowCost(),
        audit_id_factory=lambda: "00000000-0000-7000-8000-000000000104",
        clock=lambda: NOW,
        generator=GENERATOR,
    )
    return ManualAIExplanationService(
        provider_orchestrator=orchestrator,
        identity_factory=lambda: next(ids),
        clock=lambda: NOW,
    )


def test_valid_evidence_runs_existing_pipeline_once_and_returns_grounded_text():
    provider = Provider(_candidate)
    result = _service(provider).explain(_source())

    assert result.status == "available"
    assert provider.calls == 1
    assert "/evidence/strategy/decisions/0/disposition" in result.claims[0][
        "citations"
    ]


def test_provider_evidence_tracks_the_deterministic_candidate_index():
    source = _source()
    rejected = dict(source["strategy"]["decisions"][0])
    rejected["disposition"] = "rejected"
    source["strategy"]["decisions"].insert(0, rejected)

    def indexed_candidate(request):
        value = _candidate(request)
        value["claims"][0]["citations"] = [
            "/evidence/strategy/decisions/1/disposition",
            "/evidence/strategy/decisions/1/confidence",
        ]
        return value

    provider = Provider(indexed_candidate)
    result = _service(provider).explain(source)

    assert result.status == "available"
    assert provider.calls == 1
    assert "/evidence/strategy/decisions/1/disposition" in result.claims[0][
        "citations"
    ]


@pytest.mark.parametrize(
    "source_name",
    ["stale-unavailable-no-signal-with-risk.canonical.json", "no-data.canonical.json"],
)
def test_stale_or_incomplete_evidence_refuses_before_provider(source_name):
    provider = Provider(AssertionError("provider must not run"))
    result = _service(provider).explain(_source(source_name))
    assert result.status == "unavailable"
    assert provider.calls == 0


@pytest.mark.parametrize(
    "defect",
    ["untrusted", "misaligned", "malformed_timestamp", "ambiguous", "incomplete"],
)
def test_manual_product_trust_defects_reject_before_provider(defect):
    source = _source()
    if defect == "untrusted":
        source["trust"]["status"] = "untrusted"
    elif defect == "misaligned":
        source["market"]["latest_bar"]["occurred_at"] = "2026-08-06T12:05:00.000000Z"
    elif defect == "malformed_timestamp":
        malformed = "not-a-timestamp"
        source["source_trust"]["freshness"]["latest_closed_at"] = malformed
        source["market"]["latest_closed_at"] = malformed
        source["market"]["latest_bar"]["occurred_at"] = malformed
    elif defect == "ambiguous":
        source["strategy"]["decisions"].append(
            dict(source["strategy"]["decisions"][0])
        )
    else:
        source["strategy"]["decisions"][0]["stop"] = None
    provider = Provider(AssertionError("provider must not run"))
    result = _service(provider).explain(source)
    assert result.status == "unavailable"
    assert provider.calls == 0


@pytest.mark.parametrize(
    "candidate",
    [
        ProviderTimeoutError("credential=secret"),
        RuntimeError("credential=secret internal=private"),
        {"malformed": True},
    ],
)
def test_provider_failure_or_malformed_output_is_sanitized(candidate):
    provider = Provider(candidate)
    result = _service(provider).explain(_source())
    assert result.status == "unavailable"
    assert provider.calls == 1
    assert "secret" not in repr(result)


@pytest.mark.parametrize(
    "hostile_text",
    ["Buy 3 contracts now at 99999.", "The deterministic strategy state is rejected."],
)
def test_numeric_invention_and_contradictory_state_are_rejected(hostile_text):
    def hostile(request):
        value = _candidate(request)
        value["summary"] = hostile_text
        value["claims"][0]["text"] = hostile_text
        return value

    provider = Provider(hostile)
    result = _service(provider).explain(_source())
    assert result.status == "unavailable"
    assert provider.calls == 1
    assert hostile_text not in repr(result)
