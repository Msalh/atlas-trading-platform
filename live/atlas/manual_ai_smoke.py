"""Internal same-process observability and CLI for one manual AI smoke invocation.

This module exposes no HTTP route.  Its CLI owns one fixed canonical input and
emits only a bounded, content-free report.
"""

from __future__ import annotations

import copy
import json
import os
import re
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from atlas.manual_ai_advisory import ManualAIExplanationService
from atlas_ai_analysis.errors import OutputRejectionClassification
from atlas_ai_orchestration import (
    ProviderFailureClassification,
    ProviderFailureDiagnostics,
    ProviderTransportDiagnostics,
)

if __name__ == "__main__":
    sys.modules.setdefault("atlas.manual_ai_smoke", sys.modules[__name__])

_STAGES = {
    ProviderFailureClassification.CONNECTIVITY: "during_transport",
    ProviderFailureClassification.TIMEOUT: "during_transport",
    ProviderFailureClassification.HTTP_4XX: "during_transport",
    ProviderFailureClassification.HTTP_429: "during_transport",
    ProviderFailureClassification.HTTP_5XX: "during_transport",
    ProviderFailureClassification.RESPONSE_TOO_LARGE: "during_transport",
    ProviderFailureClassification.RESPONSE_DECODE: "response_parsing_schema_handling",
    ProviderFailureClassification.PHASE18B_INVALID_OUTPUT: (
        "authoritative_phase18b_validation"
    ),
}
_CANONICAL_INPUT = (
    Path(__file__).resolve().parents[1]
    / "specs"
    / "trader_now_snapshot"
    / "v1"
    / "golden"
    / "complete-current-candidate.canonical.json"
)
_REPORT_KEYS = frozenset(
    {
        "schema_version",
        "public_result",
        "provider_transport_count",
        "failure_counters",
        "phase18b_rule_counters",
        "failure_stage",
        "nonzero_failure_category",
        "nonzero_phase18b_rule",
        "deterministic_authority_unchanged",
        "authoritative_output_fields_validated",
        "diagnostic_status",
        "snapshot_collected_before_teardown",
    }
)
_FALLBACK_JSON = (
    '{"authoritative_output_fields_validated":0,'
    '"deterministic_authority_unchanged":false,'
    '"diagnostic_status":"failed_closed","failure_counters":{},'
    '"failure_stage":null,"nonzero_failure_category":null,'
    '"nonzero_phase18b_rule":null,"phase18b_rule_counters":{},'
    '"provider_transport_count":0,"public_result":"analysis_unavailable",'
    '"schema_version":"manual_ai_one_shot_diagnostic.v1",'
    '"snapshot_collected_before_teardown":false}'
)

EXIT_COMPLETED = 0
EXIT_ANALYSIS_UNAVAILABLE = 2
EXIT_PREFLIGHT_BLOCKED = 3
EXIT_INTERNAL_FAIL_CLOSED = 4
_INTEGER_TEXT = re.compile(r"(?:0|[1-9][0-9]*)\Z", re.ASCII)
_DECIMAL_TEXT = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z", re.ASCII)


class OneShotDiagnosticError(RuntimeError):
    """Fixed, content-free failure from misuse of the one-shot harness."""


@dataclass(frozen=True, slots=True)
class OneShotDiagnosticReport:
    public_result: Literal["completed", "analysis_unavailable"]
    provider_transport_count: int
    failure_counters: tuple[tuple[str, int], ...]
    phase18b_rule_counters: tuple[tuple[str, int], ...]
    failure_stage: str | None
    nonzero_failure_category: str | None
    nonzero_phase18b_rule: str | None
    deterministic_authority_unchanged: bool
    authoritative_output_fields_validated: int
    diagnostic_status: Literal["complete", "failed_closed"]
    snapshot_collected_before_teardown: bool

    def to_dict(self) -> dict[str, object]:
        """Return only the fixed bounded report schema."""

        return {
            "schema_version": "manual_ai_one_shot_diagnostic.v1",
            "public_result": self.public_result,
            "provider_transport_count": self.provider_transport_count,
            "failure_counters": dict(self.failure_counters),
            "phase18b_rule_counters": dict(self.phase18b_rule_counters),
            "failure_stage": self.failure_stage,
            "nonzero_failure_category": self.nonzero_failure_category,
            "nonzero_phase18b_rule": self.nonzero_phase18b_rule,
            "deterministic_authority_unchanged": (
                self.deterministic_authority_unchanged
            ),
            "authoritative_output_fields_validated": (
                self.authoritative_output_fields_validated
            ),
            "diagnostic_status": self.diagnostic_status,
            "snapshot_collected_before_teardown": (
                self.snapshot_collected_before_teardown
            ),
        }


class ManualAIOneShotRunner:
    """Invoke once and snapshot sanitized counters before returning."""

    __slots__ = ("_diagnostics", "_service", "_transport", "_used")

    def __init__(
        self,
        *,
        service: ManualAIExplanationService,
        diagnostics: ProviderFailureDiagnostics,
        transport_diagnostics: ProviderTransportDiagnostics,
    ) -> None:
        self._service = service
        self._diagnostics = diagnostics
        self._transport = transport_diagnostics
        self._used = False

    def run(self, trader_now_response: Mapping[str, object]) -> OneShotDiagnosticReport:
        if self._used:
            raise OneShotDiagnosticError("one-shot runner already used") from None
        self._used = True
        before = _authoritative_projection(trader_now_response)
        public_result: Literal["completed", "analysis_unavailable"] = (
            "analysis_unavailable"
        )
        validated_fields = 0
        try:
            explanation, validated_fields = (
                self._service._explain_with_validation_count(trader_now_response)
            )
            if explanation.status == "available":
                public_result = "completed"
        except Exception:  # noqa: BLE001 - report remains closed and content-free
            public_result = "analysis_unavailable"
        finally:
            after = _authoritative_projection(trader_now_response)
            authority_unchanged = before is not None and before == after
            report = self._snapshot(public_result, authority_unchanged, validated_fields)
        return report

    def _snapshot(
        self,
        public_result: Literal["completed", "analysis_unavailable"],
        authority_unchanged: bool,
        validated_fields: int,
    ) -> OneShotDiagnosticReport:
        try:
            transports = self._transport.snapshot()
            failures = self._diagnostics.snapshot()
            rules = self._diagnostics.phase18b_snapshot()
            failure_items = tuple((item.value, failures[item]) for item in ProviderFailureClassification)
            rule_items = tuple((item.value, rules[item]) for item in OutputRejectionClassification)
        except Exception:  # noqa: BLE001 - never disclose snapshot failures
            return _failed_snapshot(public_result, authority_unchanged)

        nonzero_failures = [item for item, count in failures.items() if count]
        nonzero_rules = [item for item, count in rules.items() if count]
        stage = _STAGES.get(nonzero_failures[0]) if len(nonzero_failures) == 1 else None
        if transports == 0 and not nonzero_failures:
            stage = "before_transport"
        completed = public_result == "completed"
        coherent = (
            transports == 1
            and authority_unchanged
            and ((completed and validated_fields == 11) or (not completed and validated_fields == 0))
            and (
                (completed and not nonzero_failures and not nonzero_rules)
                or (
                    not completed
                    and len(nonzero_failures) == 1
                    and sum(failures.values()) == 1
                    and len(nonzero_rules) <= 1
                    and sum(rules.values()) <= 1
                    and stage is not None
                    and (
                        nonzero_failures[0]
                        is not ProviderFailureClassification.PHASE18B_INVALID_OUTPUT
                        or len(nonzero_rules) == 1
                    )
                )
            )
        )
        return OneShotDiagnosticReport(
            public_result=public_result,
            provider_transport_count=transports,
            failure_counters=failure_items,
            phase18b_rule_counters=rule_items,
            failure_stage=stage,
            nonzero_failure_category=(
                nonzero_failures[0].value if len(nonzero_failures) == 1 else None
            ),
            nonzero_phase18b_rule=(
                nonzero_rules[0].value if len(nonzero_rules) == 1 else None
            ),
            deterministic_authority_unchanged=authority_unchanged,
            authoritative_output_fields_validated=(
                validated_fields if type(validated_fields) is int else 0
            ),
            diagnostic_status="complete" if coherent else "failed_closed",
            snapshot_collected_before_teardown=True,
        )


def _authoritative_projection(response: Mapping[str, object]) -> tuple[object, ...] | None:
    """Copy only action/Entry/SL/TP/confidence for before/after comparison."""

    try:
        market = response["market"]
        strategy = response["strategy"]
        if not isinstance(market, Mapping) or not isinstance(strategy, Mapping):
            return None
        latest_bar = market["latest_bar"]
        decisions = strategy["decisions"]
        if not isinstance(latest_bar, Mapping) or not isinstance(decisions, (list, tuple)):
            return None
        candidates = [
            item
            for item in decisions
            if isinstance(item, Mapping) and item.get("disposition") == "candidate"
        ]
        if len(candidates) != 1:
            return None
        candidate = candidates[0]
        return copy.deepcopy(
            (
                candidate.get("direction"),
                latest_bar.get("close"),
                candidate.get("stop"),
                candidate.get("target"),
                candidate.get("confidence"),
            )
        )
    except Exception:  # noqa: BLE001 - no source detail enters the report
        return None


def _failed_snapshot(
    public_result: Literal["completed", "analysis_unavailable"],
    authority_unchanged: bool,
) -> OneShotDiagnosticReport:
    return OneShotDiagnosticReport(
        public_result=public_result,
        provider_transport_count=0,
        failure_counters=tuple((item.value, 0) for item in ProviderFailureClassification),
        phase18b_rule_counters=tuple((item.value, 0) for item in OutputRejectionClassification),
        failure_stage=None,
        nonzero_failure_category=None,
        nonzero_phase18b_rule=None,
        deterministic_authority_unchanged=authority_unchanged,
        authoritative_output_fields_validated=0,
        diagnostic_status="failed_closed",
        snapshot_collected_before_teardown=False,
    )


def _canonical_input() -> Mapping[str, object]:
    sealed = json.loads(_CANONICAL_INPUT.read_text(encoding="utf-8"))
    if type(sealed) is not dict or type(sealed.get("evidence")) is not dict:
        raise OneShotDiagnosticError("canonical input unavailable") from None
    source: dict[str, object] = {
        "schema_version": "trader_now_response.v2",
        "domain_schema_version": "trader_now.v2",
    }
    source.update(sealed["evidence"])
    return source


def _runtime_runner() -> ManualAIOneShotRunner | None:
    from atlas.config import settings
    from atlas.manual_ai_runtime import build_manual_ai_one_shot_runner

    return build_manual_ai_one_shot_runner(settings)


def _preflight(environment: Mapping[str, str]) -> dict[str, bool]:
    def positive_int(name: str, maximum: int) -> bool:
        try:
            value = environment.get(name, "")
            return (
                _INTEGER_TEXT.fullmatch(value) is not None
                and 0 < int(value) <= maximum
            )
        except Exception:  # noqa: BLE001 - booleans only
            return False

    def bounded_number(name: str, minimum: float, maximum: float) -> bool:
        try:
            value = environment.get(name, "")
            if _DECIMAL_TEXT.fullmatch(value) is None:
                return False
            parsed = float(value)
            return minimum <= parsed <= maximum
        except Exception:  # noqa: BLE001 - booleans only
            return False

    return {
        "environment_ok": environment.get("ENVIRONMENT") == "development",
        "provider_enabled_ok": (
            environment.get("ATLAS_AI_PROVIDER_ENABLED") == "true"
        ),
        "api_key_present": bool(environment.get("ATLAS_AI_PROVIDER_API_KEY")),
        "model_ok": (
            environment.get("ATLAS_AI_PROVIDER_MODEL") == "gpt-5.6-terra"
        ),
        "timeout_ok": bounded_number(
            "ATLAS_AI_PROVIDER_TIMEOUT_SECONDS", 0.000001, 60.0
        ),
        "request_limit_ok": positive_int(
            "ATLAS_AI_PROVIDER_MAX_REQUEST_BYTES", 65_536
        ),
        "response_limit_ok": positive_int(
            "ATLAS_AI_PROVIDER_MAX_RESPONSE_BYTES", 131_072
        ),
        "output_tokens_ok": positive_int(
            "ATLAS_AI_PROVIDER_MAX_OUTPUT_TOKENS", 4_096
        ),
        "cost_ceiling_ok": bounded_number(
            "ATLAS_AI_PROVIDER_MAX_ESTIMATED_COST", 0.081920, 0.12
        ),
        "canonical_input_present": _CANONICAL_INPUT.is_file(),
        "provider_retries_disabled": True,
        "http_transport_retries_disabled": True,
    }


def _emit_json(value: Mapping[str, object], write: Callable[[str], object]) -> bool:
    try:
        if set(value) != _REPORT_KEYS:
            raise ValueError
        encoded = json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
        write(encoded + "\n")
        return True
    except Exception:  # noqa: BLE001 - fixed fallback only
        try:
            write(_FALLBACK_JSON + "\n")
        except Exception:  # noqa: BLE001 - no safe output channel remains
            pass
        return False


def _emit_preflight(value: Mapping[str, bool], write: Callable[[str], object]) -> bool:
    try:
        if not value or any(type(item) is not bool for item in value.values()):
            raise ValueError
        write(json.dumps(value, separators=(",", ":"), sort_keys=True) + "\n")
        return True
    except Exception:  # noqa: BLE001 - preflight must disclose nothing else
        return False


def main(
    argv: list[str] | None = None,
    *,
    environment: Mapping[str, str] | None = None,
    runner_factory: Callable[[], ManualAIOneShotRunner | None] = _runtime_runner,
    input_loader: Callable[[], Mapping[str, object]] = _canonical_input,
    write: Callable[[str], object] = sys.stdout.write,
) -> int:
    """Run the fixed CLI contract once, without accepting provider-controlled input."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments == ["--preflight"]:
        checks = _preflight(os.environ if environment is None else environment)
        emitted = _emit_preflight(checks, write)
        return (
            EXIT_COMPLETED
            if emitted and all(checks.values())
            else EXIT_PREFLIGHT_BLOCKED
        )
    if arguments:
        _emit_json(_failed_snapshot("analysis_unavailable", False).to_dict(), write)
        return EXIT_INTERNAL_FAIL_CLOSED

    try:
        source = input_loader()
        runner = runner_factory()
        if type(runner) is not ManualAIOneShotRunner:
            raise OneShotDiagnosticError("runtime unavailable")
        report = runner.run(source)
        if type(report) is not OneShotDiagnosticReport:
            raise OneShotDiagnosticError("snapshot unavailable")
        rendered = report.to_dict()
    except Exception:  # noqa: BLE001 - never disclose operational diagnostics
        rendered = _failed_snapshot("analysis_unavailable", False).to_dict()
        _emit_json(rendered, write)
        return EXIT_INTERNAL_FAIL_CLOSED

    if not _emit_json(rendered, write) or report.diagnostic_status != "complete":
        return EXIT_INTERNAL_FAIL_CLOSED
    if report.public_result == "completed":
        return EXIT_COMPLETED
    return EXIT_ANALYSIS_UNAVAILABLE


if __name__ == "__main__":
    raise SystemExit(main())
