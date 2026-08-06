"""Manual-only AI explanation over one validated TraderNow response.

This module is deliberately an injected composition boundary.  It does not
configure a provider, read credentials, persist data, or schedule work.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from atlas_ai_analysis import AnalysisInputIdentity
from atlas_ai_orchestration import CompletedOutcome, ProviderOrchestrator
from atlas_ai_service import AIServiceOrchestrator, EvidenceClient
from atlas_snapshot import SnapshotRecordIdentity, project, serialize

_BASE_EVIDENCE_PATHS = (
    "/evidence/identity",
    "/evidence/trust",
    "/evidence/market/latest_closed_at",
    "/evidence/market/latest_bar",
    "/evidence/source_trust",
    "/evidence/setups",
    "/evidence/context",
    "/evidence/risk",
    "/evidence/decision/availability",
)


@dataclass(frozen=True, slots=True)
class ManualAIExplanation:
    status: Literal["available", "unavailable"]
    summary: str | None = None
    claims: tuple[Mapping[str, Any], ...] = ()
    limitations: tuple[str, ...] = ()
    reason: Literal["analysis_unavailable"] | None = None


class _SingleSnapshotTransport:
    def __init__(self, snapshot_id: str, payload: bytes) -> None:
        self._snapshot_id = snapshot_id
        self._payload = payload

    def fetch_snapshot(self, snapshot_id: str) -> bytes:
        if snapshot_id != self._snapshot_id:
            raise LookupError("snapshot unavailable")
        return self._payload


class ManualAIExplanationService:
    """Run the existing 18C -> 18D -> 18B path for one manual response."""

    def __init__(
        self,
        *,
        provider_orchestrator: ProviderOrchestrator,
        identity_factory: Callable[[], str],
        clock: Callable[[], str],
    ) -> None:
        self._provider_orchestrator = provider_orchestrator
        self._identity_factory = identity_factory
        self._clock = clock

    def explain(self, trader_now_response: Mapping[str, Any]) -> ManualAIExplanation:
        try:
            evidence_paths = _manual_evidence_paths(trader_now_response)
            if evidence_paths is None:
                return unavailable_explanation()
            snapshot_id = self._identity_factory()
            snapshot = project(
                trader_now_response,
                SnapshotRecordIdentity(snapshot_id=snapshot_id, created_at=self._clock()),
            )
            evidence = AIServiceOrchestrator(
                EvidenceClient(_SingleSnapshotTransport(snapshot_id, serialize(snapshot)))
            ).evaluate(
                snapshot_id,
                "strategy_explanation",
                AnalysisInputIdentity(self._identity_factory(), self._clock()),
                evidence_paths=evidence_paths,
            )
            outcome = self._provider_orchestrator.run(evidence)
            if not isinstance(outcome, CompletedOutcome):
                return unavailable_explanation()
            output = outcome.output
            return ManualAIExplanation(
                status="available",
                summary=output["summary"],
                claims=tuple(output["claims"]),
                limitations=tuple(output["limitations"]),
            )
        except Exception:  # noqa: BLE001 - fail closed without retaining diagnostics
            return unavailable_explanation()


def unavailable_explanation() -> ManualAIExplanation:
    return ManualAIExplanation(status="unavailable", reason="analysis_unavailable")


def _manual_evidence_paths(
    response: Mapping[str, Any],
) -> tuple[str, ...] | None:
    """Apply the product gate and bind evidence to the deterministic candidate."""
    try:
        identity = response["identity"]
        trust = response["trust"]
        source_trust = response["source_trust"]
        freshness = source_trust["freshness"]
        market = response["market"]
        latest_bar = market["latest_bar"]
        strategy = response["strategy"]
        decisions = strategy["decisions"]
        if not all(
            isinstance(value, Mapping)
            for value in (
                identity,
                trust,
                source_trust,
                freshness,
                market,
                latest_bar,
                strategy,
            )
        ):
            return None
        if (
            identity.get("product") != "MNQ"
            or identity.get("timeframe") != "5m"
            or trust.get("status") != "trusted"
            or source_trust.get("overall") != "trusted"
            or source_trust.get("structural_validity") != "valid"
            or freshness.get("status") != "current"
            or strategy.get("availability", {}).get("status") != "available"
        ):
            return None
        latest_closed = freshness.get("latest_closed_at")
        if (
            not isinstance(latest_closed, str)
            or market.get("latest_closed_at") != latest_closed
            or latest_bar.get("occurred_at") != latest_closed
        ):
            return None
        if not isinstance(decisions, (list, tuple)):
            return None
        candidates = [
            (index, item)
            for index, item in enumerate(decisions)
            if isinstance(item, Mapping) and item.get("disposition") == "candidate"
        ]
        if len(candidates) > 1:
            return None
        if candidates:
            candidate_index, candidate = candidates[0]
            if (
                candidate.get("direction") not in {"long", "short"}
                or not isinstance(candidate.get("setup_ids"), (list, tuple))
                or not candidate.get("setup_ids")
                or candidate.get("stop") is None
                or candidate.get("target") is None
                or candidate.get("confidence") is None
            ):
                return None
            return _BASE_EVIDENCE_PATHS + (
                f"/evidence/strategy/decisions/{candidate_index}/disposition",
                f"/evidence/strategy/decisions/{candidate_index}/confidence",
            )
        return _BASE_EVIDENCE_PATHS + ("/evidence/strategy/decisions",)
    except (KeyError, TypeError, AttributeError):
        return None


def explanation_to_dict(value: ManualAIExplanation) -> dict[str, Any]:
    return {
        "status": value.status,
        "summary": value.summary,
        "claims": [dict(claim) for claim in value.claims],
        "limitations": list(value.limitations),
        "reason": value.reason,
    }
