"""Internal same-process observability for one manual AI smoke invocation.

This module has no CLI entry point and exposes no HTTP route.  It accepts only
already-composed runtime objects and emits a fixed, content-free report.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from atlas.manual_ai_advisory import ManualAIExplanationService
from atlas_ai_analysis.errors import OutputRejectionClassification
from atlas_ai_orchestration import (
    ProviderFailureClassification,
    ProviderFailureDiagnostics,
    ProviderTransportDiagnostics,
)

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
