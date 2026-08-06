"""Offline qualification for bounded same-process one-shot diagnostics."""

import inspect
import io
import json
import runpy
import sys
from pathlib import Path

import pytest

from atlas.manual_ai_advisory import ManualAIExplanation
import atlas.manual_ai_smoke as smoke_module
from atlas.manual_ai_smoke import (
    EXIT_ANALYSIS_UNAVAILABLE,
    EXIT_COMPLETED,
    EXIT_INTERNAL_FAIL_CLOSED,
    EXIT_PREFLIGHT_BLOCKED,
    ManualAIOneShotRunner,
    OneShotDiagnosticError,
    main,
)
from atlas_ai_analysis.errors import OutputRejectionClassification
from atlas_ai_orchestration import (
    ProviderFailureClassification,
    ProviderFailureDiagnostics,
    ProviderTransportDiagnostics,
)
from atlas_ai_orchestration.openai_adapter import OpenAIProviderAdapter

SENTINEL = "credential prompt payload response evidence header exception request-id"
ROOT = Path(__file__).resolve().parents[1]


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


def _environment():
    return {
        "ENVIRONMENT": "development",
        "ATLAS_AI_PROVIDER_ENABLED": "true",
        "ATLAS_AI_PROVIDER_API_KEY": "synthetic-present",
        "ATLAS_AI_PROVIDER_MODEL": "gpt-5.6-terra",
        "ATLAS_AI_PROVIDER_TIMEOUT_SECONDS": "60",
        "ATLAS_AI_PROVIDER_MAX_REQUEST_BYTES": "65536",
        "ATLAS_AI_PROVIDER_MAX_RESPONSE_BYTES": "131072",
        "ATLAS_AI_PROVIDER_MAX_OUTPUT_TOKENS": "4096",
        "ATLAS_AI_PROVIDER_MAX_ESTIMATED_COST": "0.12",
    }


def _run_cli(runner, *, argv=None, input_loader=_source):
    output = []
    code = main(
        [] if argv is None else argv,
        runner_factory=lambda: runner,
        input_loader=input_loader,
        write=output.append,
    )
    return code, output


def test_module_entry_point_emits_one_bounded_json_object_without_runtime_access(
    monkeypatch,
):
    output = io.StringIO()
    monkeypatch.setattr(sys, "argv", ["manual_ai_smoke", "--unsupported"])
    monkeypatch.setattr(sys, "stdout", output)

    with pytest.raises(SystemExit) as stopped:
        runpy.run_module("atlas.manual_ai_smoke", run_name="__main__")

    assert stopped.value.code == EXIT_INTERNAL_FAIL_CLOSED
    assert len(output.getvalue().splitlines()) == 1
    assert json.loads(output.getvalue())["diagnostic_status"] == "failed_closed"


def test_cli_owns_the_exact_committed_canonical_input():
    expected = (
        ROOT
        / "specs"
        / "trader_now_snapshot"
        / "v1"
        / "golden"
        / "complete-current-candidate.canonical.json"
    )

    assert smoke_module._CANONICAL_INPUT == expected


def test_cli_completed_report_is_bounded_and_exit_zero():
    runner, service = _runner(result=ManualAIExplanation(status="available", summary="safe"))

    code, output = _run_cli(runner)
    rendered = json.loads(output[0])

    assert code == EXIT_COMPLETED
    assert service.calls == 1
    assert len(output) == 1
    assert set(rendered) == smoke_module._REPORT_KEYS
    assert rendered["authoritative_output_fields_validated"] == 11


@pytest.mark.parametrize(
    ("category", "rule", "stage"),
    (
        (ProviderFailureClassification.TIMEOUT, None, "during_transport"),
        (
            ProviderFailureClassification.RESPONSE_DECODE,
            None,
            "response_parsing_schema_handling",
        ),
        (
            ProviderFailureClassification.PHASE18B_INVALID_OUTPUT,
            OutputRejectionClassification.INVALID_SUMMARY,
            "authoritative_phase18b_validation",
        ),
    ),
)
def test_cli_reports_each_post_send_failure_stage(category, rule, stage):
    runner, service = _runner(category=category, rule=rule)

    code, output = _run_cli(runner)
    rendered = json.loads(output[0])

    assert code == EXIT_ANALYSIS_UNAVAILABLE
    assert service.calls == 1
    assert rendered["provider_transport_count"] == 1
    assert rendered["failure_stage"] == stage


def test_cli_before_transport_state_fails_closed_without_attempt():
    runner, service = _runner(calls=0)

    code, output = _run_cli(runner)

    assert code == EXIT_INTERNAL_FAIL_CLOSED
    assert service.calls == 1
    assert json.loads(output[0])["failure_stage"] == "before_transport"


def test_cli_construction_and_input_failures_are_fixed_and_fail_closed():
    no_runner, no_runner_output = _run_cli(None)
    bad_input, bad_input_output = _run_cli(
        None, input_loader=lambda: (_ for _ in ()).throw(RuntimeError(SENTINEL))
    )

    assert no_runner == bad_input == EXIT_INTERNAL_FAIL_CLOSED
    assert SENTINEL not in "".join(no_runner_output + bad_input_output)
    assert all(json.loads(item)["provider_transport_count"] == 0 for item in no_runner_output + bad_input_output)


def test_cli_serialization_failure_uses_fixed_fallback(monkeypatch):
    runner, service = _runner(result=ManualAIExplanation(status="available", summary="safe"))
    monkeypatch.setattr(smoke_module.json, "dumps", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError(SENTINEL)))

    code, output = _run_cli(runner)

    assert code == EXIT_INTERNAL_FAIL_CLOSED
    assert service.calls == 1
    assert output == [smoke_module._FALLBACK_JSON + "\n"]
    assert SENTINEL not in output[0]


def test_preflight_is_boolean_only_and_never_constructs_or_sends():
    output = []

    code = main(
        ["--preflight"],
        environment=_environment(),
        runner_factory=lambda: pytest.fail("preflight must not construct runtime"),
        input_loader=lambda: pytest.fail("preflight must not load input"),
        write=output.append,
    )
    rendered = json.loads(output[0])

    assert code == EXIT_COMPLETED
    assert rendered
    assert all(type(value) is bool for value in rendered.values())


def test_preflight_blocked_exit_code_is_stable():
    output = []

    code = main(["--preflight"], environment={}, write=output.append)

    assert code == EXIT_PREFLIGHT_BLOCKED
    assert all(type(value) is bool for value in json.loads(output[0]).values())


@pytest.mark.parametrize(
    ("name", "value"),
    (
        ("ATLAS_AI_PROVIDER_TIMEOUT_SECONDS", "6e1"),
        ("ATLAS_AI_PROVIDER_MAX_REQUEST_BYTES", "065536"),
        ("ATLAS_AI_PROVIDER_MAX_ESTIMATED_COST", " 0.12"),
    ),
)
def test_preflight_numeric_syntax_matches_runtime_fail_closed_rules(name, value):
    environment = _environment()
    environment[name] = value
    output = []

    code = main(["--preflight"], environment=environment, write=output.append)

    assert code == EXIT_PREFLIGHT_BLOCKED


def test_normal_cli_uses_no_real_network_and_runs_exactly_once(monkeypatch):
    monkeypatch.setattr(
        "httpx.Client.send",
        lambda *_args, **_kwargs: pytest.fail("real network is prohibited"),
    )
    runner, service = _runner(category=ProviderFailureClassification.CONNECTIVITY)

    code, _output = _run_cli(runner)

    assert code == EXIT_ANALYSIS_UNAVAILABLE
    assert service.calls == 1
