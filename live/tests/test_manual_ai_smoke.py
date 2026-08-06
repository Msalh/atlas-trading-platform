"""Offline qualification for bounded same-process one-shot diagnostics."""

import inspect
import json

import pytest

from atlas.manual_ai_advisory import ManualAIExplanation
from atlas.manual_ai_smoke import ManualAIOneShotRunner, OneShotDiagnosticError
from atlas_ai_analysis.errors import OutputRejectionClassification
from atlas_ai_orchestration import (
    ProviderFailureClassification,
    ProviderFailureDiagnostics,
    ProviderTransportDiagnostics,
)
from atlas_ai_orchestration.openai_adapter import OpenAIProviderAdapter

SENTINEL = "credential prompt payload response evidence header exception request-id"


def _source():
    return {
        "market": {"latest_bar": {"close": {"value": "100", "tick_size": "0.25"}}},
        "strategy": {
            "decisions": [
                {
                    "disposition": "candidate",
                    "direction": "long",
                    "stop": {"value": "95", "tick_size": "0.25"},
                    "target": {"value": "110", "tick_size": "0.25"},
                    "confidence": "0.80",
                }
            ]
        },
    }


class SyntheticService:
    def __init__(self, result, on_call=None):
        self.result = result
        self.on_call = on_call
        self.calls = 0

    def explain(self, _source):
        self.calls += 1
        if self.on_call is not None:
            self.on_call()
        if isinstance(self.result, Exception):
            raise self.result
        return self.result

    def _explain_with_validation_count(self, source):
        result = self.explain(source)
        return result, 11 if result.status == "available" else 0


def _runner(*, category=None, rule=None, result=None, calls=1, diagnostics=None):
    failures = diagnostics or ProviderFailureDiagnostics()
    transports = ProviderTransportDiagnostics()

    def observe():
        for _ in range(calls):
            transports.record_attempt()
        if category is not None:
            failures.record(category)
        if rule is not None:
            failures.record_phase18b(rule)

    service = SyntheticService(
        result or ManualAIExplanation(status="unavailable", reason="analysis_unavailable"),
        observe,
    )
    return (
        ManualAIOneShotRunner(
            service=service,
            diagnostics=failures,
            transport_diagnostics=transports,
        ),
        service,
    )


@pytest.mark.parametrize(
    ("category", "stage"),
    (
        (ProviderFailureClassification.CONNECTIVITY, "during_transport"),
        (ProviderFailureClassification.TIMEOUT, "during_transport"),
        (ProviderFailureClassification.HTTP_4XX, "during_transport"),
        (ProviderFailureClassification.HTTP_429, "during_transport"),
        (ProviderFailureClassification.HTTP_5XX, "during_transport"),
        (ProviderFailureClassification.RESPONSE_TOO_LARGE, "during_transport"),
        (
            ProviderFailureClassification.RESPONSE_DECODE,
            "response_parsing_schema_handling",
        ),
    ),
)
def test_transport_timeout_http_and_parsing_failures_are_closed(category, stage):
    runner, _ = _runner(category=category)

    report = runner.run(_source())

    assert report.public_result == "analysis_unavailable"
    assert report.provider_transport_count == 1
    assert report.failure_stage == stage
    assert report.nonzero_failure_category == category.value
    assert report.nonzero_phase18b_rule is None
    assert report.diagnostic_status == "complete"


@pytest.mark.parametrize("rule", tuple(OutputRejectionClassification))
def test_every_phase18b_rejection_is_reported_as_one_closed_rule(rule):
    runner, _ = _runner(
        category=ProviderFailureClassification.PHASE18B_INVALID_OUTPUT,
        rule=rule,
    )

    report = runner.run(_source())

    assert report.failure_stage == "authoritative_phase18b_validation"
    assert report.nonzero_phase18b_rule == rule.value
    assert sum(dict(report.phase18b_rule_counters).values()) == 1
    assert report.diagnostic_status == "complete"


def test_unexpected_classifier_or_validator_failure_fails_closed():
    runner, _ = _runner(category=ProviderFailureClassification.UNKNOWN)

    report = runner.run(_source())

    assert report.public_result == "analysis_unavailable"
    assert report.failure_stage is None
    assert report.diagnostic_status == "failed_closed"


def test_completed_analysis_validates_all_eleven_fields():
    runner, _ = _runner(result=ManualAIExplanation(status="available", summary="safe"))

    report = runner.run(_source())

    assert report.public_result == "completed"
    assert report.authoritative_output_fields_validated == 11
    assert report.deterministic_authority_unchanged is True
    assert report.diagnostic_status == "complete"
    assert sum(dict(report.failure_counters).values()) == 0
    assert sum(dict(report.phase18b_rule_counters).values()) == 0


@pytest.mark.parametrize("calls", (0, 2))
def test_transport_count_other_than_exactly_one_fails_closed(calls):
    runner, _ = _runner(
        category=ProviderFailureClassification.CONNECTIVITY,
        calls=calls,
    )

    assert runner.run(_source()).diagnostic_status == "failed_closed"


def test_zero_transport_without_failure_counter_is_classified_before_transport():
    runner, _ = _runner(calls=0)

    report = runner.run(_source())

    assert report.failure_stage == "before_transport"
    assert report.diagnostic_status == "failed_closed"


def test_multiple_phase18b_rules_fail_closed():
    diagnostics = ProviderFailureDiagnostics()
    diagnostics.record_phase18b(OutputRejectionClassification.INVALID_SUMMARY)
    runner, _ = _runner(
        category=ProviderFailureClassification.PHASE18B_INVALID_OUTPUT,
        rule=OutputRejectionClassification.INVALID_CLAIM_TEXT,
        diagnostics=diagnostics,
    )

    report = runner.run(_source())

    assert report.nonzero_phase18b_rule is None
    assert report.diagnostic_status == "failed_closed"


def test_runner_cannot_retry_or_run_twice():
    runner, service = _runner(category=ProviderFailureClassification.TIMEOUT)
    runner.run(_source())

    with pytest.raises(OneShotDiagnosticError, match="one-shot runner already used"):
        runner.run(_source())

    assert service.calls == 1


def test_transport_retries_remain_explicitly_zero():
    source = inspect.getsource(OpenAIProviderAdapter._transport)
    assert "HTTPTransport(retries=0)" in source


def test_snapshot_is_collected_after_handled_result_and_before_return():
    events = []

    class ObservedDiagnostics(ProviderFailureDiagnostics):
        def snapshot(self):
            events.append("snapshot")
            return super().snapshot()

    diagnostics = ObservedDiagnostics()
    runner, service = _runner(
        category=ProviderFailureClassification.TIMEOUT,
        diagnostics=diagnostics,
    )
    original = service.on_call

    def called():
        events.append("invoke")
        original()
        events.append("handled")

    service.on_call = called
    report = runner.run(_source())
    events.append("returned")

    assert events == ["invoke", "handled", "snapshot", "returned"]
    assert report.snapshot_collected_before_teardown is True


def test_snapshot_failure_returns_only_a_bounded_failed_closed_report():
    class BrokenDiagnostics(ProviderFailureDiagnostics):
        def snapshot(self):
            raise RuntimeError(SENTINEL)

    runner, _ = _runner(diagnostics=BrokenDiagnostics())

    report = runner.run(_source())

    assert report.diagnostic_status == "failed_closed"
    assert report.snapshot_collected_before_teardown is False
    assert SENTINEL not in json.dumps(report.to_dict())


def test_reports_are_bounded_and_never_include_sensitive_fields_or_values():
    runner, service = _runner(category=ProviderFailureClassification.CONNECTIVITY)
    service.result = RuntimeError(SENTINEL)

    rendered = json.dumps(runner.run(_source()).to_dict(), sort_keys=True)

    assert SENTINEL not in rendered
    for prohibited_key in (
        "credential",
        "prompt",
        "payload",
        "response_content",
        "evidence",
        "headers",
        "request_id",
        "exception",
    ):
        assert prohibited_key not in rendered


def test_complete_snapshots_always_contain_every_closed_counter_key():
    runner, _ = _runner(category=ProviderFailureClassification.TIMEOUT)
    report = runner.run(_source())

    assert set(dict(report.failure_counters)) == {
        item.value for item in ProviderFailureClassification
    }
    assert set(dict(report.phase18b_rule_counters)) == {
        item.value for item in OutputRejectionClassification
    }
