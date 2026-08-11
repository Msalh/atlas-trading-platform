"""Default-disabled OpenAI composition for the manual advisory route only."""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Final, Protocol

from atlas.manual_ai_advisory import ManualAIExplanationService
from atlas.manual_ai_smoke import ManualAIOneShotRunner
from atlas_ai_analysis import GeneratorIdentity
from atlas_ai_orchestration import (
    DeterministicPromptBuilder,
    ProviderFailureDiagnostics,
    ProviderOrchestrator,
    ProviderPort,
    ProviderTransportDiagnostics,
    TrustedProviderRequest,
)
from atlas_ai_orchestration.openai_adapter import (
    OpenAIAdapterPolicy,
    OpenAIProviderAdapter,
)
from atlas_ai_orchestration.pricing_authority import resolve_authoritative_pricing
from atlas_snapshot_capture import generate_uuid7

if TYPE_CHECKING:
    from atlas.config import Settings

MODEL_ID: Final = "gpt-5.6-terra"
PRICING_REFERENCE_ID: Final = "openai-gpt-5.6-terra-default-2026-08-06"
MAX_INPUT_TOKENS: Final = 16_384
MAX_REQUEST_BYTES: Final = 65_536
MAX_RESPONSE_BYTES: Final = 131_072
MAX_OUTPUT_TOKENS: Final = 4_096
MAX_ESTIMATED_COST_USD: Final = Decimal("0.12")
CONNECT_TIMEOUT_SECONDS: Final = 5.0
READ_TIMEOUT_SECONDS: Final = 45.0
MAX_DEADLINE_SECONDS: Final = 60.0
TOKENS_PER_MILLION: Final = Decimal(1_000_000)
_INTEGER_TEXT: Final = re.compile(r"(?:0|[1-9][0-9]*)\Z", re.ASCII)
_DECIMAL_TEXT: Final = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z", re.ASCII)


class AdapterFactory(Protocol):
    def __call__(
        self,
        *,
        credential_provider: Callable[[], str],
        input_token_estimator: Callable[[TrustedProviderRequest], int],
        utc_now: Callable[[], datetime],
        policy: OpenAIAdapterPolicy,
        transport_diagnostics: ProviderTransportDiagnostics | None = None,
    ) -> ProviderPort: ...


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(clock: Callable[[], datetime]) -> str:
    instant = clock()
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError
    return (
        instant.astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _estimate_input_tokens(request: TrustedProviderRequest) -> int:
    """Use UTF-8 bytes as a conservative upper estimate for input tokens."""

    values = (
        *request.trusted_instructions,
        request.untrusted_evidence_json,
        request.schema_version,
        request.output_schema_version,
        request.analysis_output_id,
        request.analysis_input_id,
        request.snapshot_id,
        request.evidence_digest,
        request.purpose,
    )
    return sum(len(value.encode("utf-8")) for value in values)


def _integer(value: object) -> int:
    if type(value) is not str or _INTEGER_TEXT.fullmatch(value) is None:
        raise ValueError
    return int(value)


def _decimal(value: object) -> float:
    if type(value) is not str or _DECIMAL_TEXT.fullmatch(value) is None:
        raise ValueError
    return float(value)


@dataclass(frozen=True, slots=True)
class ManualAIProviderConfig:
    api_key: str = field(repr=False)
    model_id: str
    deadline_seconds: float
    max_request_bytes: int
    max_response_bytes: int
    max_output_tokens: int
    max_estimated_cost_usd: float

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        allow_production: bool = False,
    ) -> ManualAIProviderConfig | None:
        if (
            settings.environment != "development" and not allow_production
        ) or settings.atlas_ai_provider_enabled != "true":
            return None
        try:
            config = cls(
                api_key=settings.atlas_ai_provider_api_key,
                model_id=settings.atlas_ai_provider_model,
                deadline_seconds=_decimal(settings.atlas_ai_provider_timeout_seconds),
                max_request_bytes=_integer(
                    settings.atlas_ai_provider_max_request_bytes
                ),
                max_response_bytes=_integer(
                    settings.atlas_ai_provider_max_response_bytes
                ),
                max_output_tokens=_integer(
                    settings.atlas_ai_provider_max_output_tokens
                ),
                max_estimated_cost_usd=_decimal(
                    settings.atlas_ai_provider_max_estimated_cost
                ),
            )
        except (AttributeError, TypeError, ValueError, OverflowError):
            return None
        if not (
            type(config.api_key) is str
            and bool(config.api_key)
            and config.model_id == MODEL_ID
            and math.isfinite(config.deadline_seconds)
            and 0 < config.deadline_seconds <= MAX_DEADLINE_SECONDS
            and type(config.max_request_bytes) is int
            and 0 < config.max_request_bytes <= MAX_REQUEST_BYTES
            and type(config.max_response_bytes) is int
            and 0 < config.max_response_bytes <= MAX_RESPONSE_BYTES
            and type(config.max_output_tokens) is int
            and 0 < config.max_output_tokens <= MAX_OUTPUT_TOKENS
            and math.isfinite(config.max_estimated_cost_usd)
            and 0 < config.max_estimated_cost_usd <= float(MAX_ESTIMATED_COST_USD)
        ):
            return None
        return config


class _RuntimeCostPolicy:
    def allows(self, request: TrustedProviderRequest) -> bool:
        return (
            type(request) is TrustedProviderRequest
            and _estimate_input_tokens(request) <= MAX_INPUT_TOKENS
        )


def _approved_pricing(now: datetime, configured_ceiling: float) -> bool:
    record = resolve_authoritative_pricing(
        provider_id="openai",
        model_id=MODEL_ID,
        service_tier="default",
        reference_id=PRICING_REFERENCE_ID,
        now=now,
    )
    if record is None:
        return False
    try:
        maximum_cost = (
            Decimal(MAX_INPUT_TOKENS)
            * Decimal(str(record.input_usd_per_million_tokens))
            + Decimal(MAX_OUTPUT_TOKENS)
            * Decimal(str(record.output_usd_per_million_tokens))
        ) / TOKENS_PER_MILLION
        ceiling = Decimal(str(configured_ceiling))
    except (InvalidOperation, ValueError):
        return False
    return maximum_cost <= ceiling <= MAX_ESTIMATED_COST_USD


def build_manual_ai_explanation_service(
    settings: Settings,
    *,
    adapter_factory: AdapterFactory = OpenAIProviderAdapter,
    clock: Callable[[], datetime] = _now,
    failure_diagnostics: ProviderFailureDiagnostics | None = None,
    transport_diagnostics: ProviderTransportDiagnostics | None = None,
) -> ManualAIExplanationService | None:
    """Build the one manual-only service, or return no attachment fail-closed."""

    try:
        config = ManualAIProviderConfig.from_settings(settings)
        if config is None:
            return None
        now = clock()
        if not _approved_pricing(now, config.max_estimated_cost_usd):
            return None
        credential = config.api_key
        provider = adapter_factory(
            credential_provider=lambda: credential,
            input_token_estimator=_estimate_input_tokens,
            utc_now=clock,
            transport_diagnostics=transport_diagnostics,
            policy=OpenAIAdapterPolicy(
                enabled=True,
                model_id=config.model_id,
                approved_model_ids=frozenset({MODEL_ID}),
                pricing_reference_id=PRICING_REFERENCE_ID,
                max_request_bytes=config.max_request_bytes,
                max_response_bytes=config.max_response_bytes,
                max_input_tokens=MAX_INPUT_TOKENS,
                max_output_tokens=config.max_output_tokens,
                connect_timeout_seconds=min(
                    CONNECT_TIMEOUT_SECONDS, config.deadline_seconds
                ),
                read_timeout_seconds=min(READ_TIMEOUT_SECONDS, config.deadline_seconds),
                deadline_seconds=config.deadline_seconds,
                max_estimated_cost_usd=config.max_estimated_cost_usd,
            ),
        )
        identity = GeneratorIdentity("openai", MODEL_ID)

        def identifier() -> str:
            return generate_uuid7(now=clock)

        def timestamp() -> str:
            return _timestamp(clock)

        orchestrator = ProviderOrchestrator(
            prompt_builder=DeterministicPromptBuilder(identifier),
            provider=provider,
            cost_policy=_RuntimeCostPolicy(),
            audit_id_factory=identifier,
            clock=timestamp,
            generator=identity,
            failure_diagnostics=failure_diagnostics or ProviderFailureDiagnostics(),
        )
        return ManualAIExplanationService(
            provider_orchestrator=orchestrator,
            identity_factory=identifier,
            clock=timestamp,
        )
    except Exception:  # noqa: BLE001 - configuration details remain private
        return None


def build_manual_ai_one_shot_runner(
    settings: Settings,
    *,
    adapter_factory: AdapterFactory = OpenAIProviderAdapter,
    clock: Callable[[], datetime] = _now,
) -> ManualAIOneShotRunner | None:
    """Build an internal same-process live-smoke runner; never used by HTTP."""

    failures = ProviderFailureDiagnostics()
    transports = ProviderTransportDiagnostics()
    service = build_manual_ai_explanation_service(
        settings,
        adapter_factory=adapter_factory,
        clock=clock,
        failure_diagnostics=failures,
        transport_diagnostics=transports,
    )
    if service is None:
        return None
    return ManualAIOneShotRunner(
        service=service,
        diagnostics=failures,
        transport_diagnostics=transports,
    )
