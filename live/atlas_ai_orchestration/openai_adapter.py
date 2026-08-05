"""Default-disabled OpenAI transport adapter for offline Phase 18E qualification."""

from __future__ import annotations

import json
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

import httpx
from atlas_ai_analysis import GeneratorIdentity

from .errors import ProviderPortError, ProviderTimeoutError, ProviderUnavailableError
from .models import JSONValue, TrustedProviderRequest
from .pricing_authority import ProviderPricingRecord, resolve_authoritative_pricing

_RESPONSES_ENDPOINT = "https://api.openai.com/v1/responses"
_PROVIDER_ID = "openai"


class InputTokenEstimator(Protocol):
    def __call__(self, request: TrustedProviderRequest) -> int: ...


class CredentialProvider(Protocol):
    def __call__(self) -> str: ...


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class OpenAIAdapterPolicy:
    model_id: str
    approved_model_ids: frozenset[str]
    pricing_reference_id: str
    enabled: bool = False
    max_request_bytes: int = 65_536
    max_response_bytes: int = 131_072
    max_input_tokens: int = 16_384
    max_output_tokens: int = 4_096
    connect_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 45.0
    deadline_seconds: float = 60.0
    max_estimated_cost_usd: float = 0.12


class OpenAIProviderAdapter:
    """Perform one bounded Responses API operation and return untrusted JSON.

    Production owns the complete ``httpx.Client`` configuration. The optional
    transport injection exists only for deterministic offline qualification; a
    preconfigured client is never accepted.
    """

    def __init__(
        self,
        *,
        credential_provider: CredentialProvider,
        input_token_estimator: InputTokenEstimator,
        policy: OpenAIAdapterPolicy,
        qualification_transport: httpx.BaseTransport | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        utc_now: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._credential_provider = credential_provider
        self._input_token_estimator = input_token_estimator
        self._policy = policy
        self._qualification_transport = qualification_transport
        self._monotonic = monotonic
        self._utc_now = utc_now

    @property
    def identity(self) -> GeneratorIdentity:
        return GeneratorIdentity(provider_id=_PROVIDER_ID, model_id=self._policy.model_id)

    def invoke(self, request: TrustedProviderRequest) -> JSONValue:
        body = self._prepare_clean(request)
        del request
        if body is None:
            self._raise_clean(ProviderPortError)
        credential = self._credential_clean()
        if credential is None:
            body = b""
            self._raise_clean(ProviderPortError)

        raw, failure = self._dispatch(body, credential)
        body = b""
        credential = None
        if failure is not None:
            self._raise_clean(failure)
        candidate, decode_failure = self._decode(raw)
        raw = b""
        if decode_failure is not None:
            self._raise_clean(decode_failure)
        return candidate

    def _prepare_clean(self, request: TrustedProviderRequest) -> bytes | None:
        body = b""
        try:
            body = self._prepare(request)
        except Exception:  # noqa: BLE001 - sanitize policy/estimator boundaries
            body = b""
        return body or None

    def _credential_clean(self) -> str | None:
        credential: str | None = None
        try:
            supplied = self._credential_provider()
            if type(supplied) is str and supplied:
                credential = supplied
            supplied = None
        except Exception:  # noqa: BLE001 - sanitize credential boundary
            credential = None
        return credential

    def _transport(self) -> httpx.BaseTransport:
        if self._qualification_transport is not None:
            return self._qualification_transport
        return httpx.HTTPTransport(retries=0)

    def _client(self) -> httpx.Client:
        policy = self._policy
        return httpx.Client(
            transport=self._transport(),
            auth=None,
            trust_env=False,
            http1=True,
            http2=False,
            proxy=None,
            mounts=None,
            timeout=httpx.Timeout(
                connect=policy.connect_timeout_seconds,
                read=policy.read_timeout_seconds,
                write=policy.read_timeout_seconds,
                pool=policy.connect_timeout_seconds,
            ),
            limits=httpx.Limits(
                max_connections=1,
                max_keepalive_connections=0,
                keepalive_expiry=0.0,
            ),
            follow_redirects=False,
            event_hooks={"request": [], "response": []},
        )

    def _dispatch(
        self,
        body: bytes,
        credential: str,
    ) -> tuple[bytes, type[ProviderPortError] | None]:
        client: httpx.Client | None = None
        request: httpx.Request | None = None
        failure: type[ProviderPortError] | None = None
        raw = b""
        try:
            client = self._client()
            request = client.build_request(
                "POST",
                _RESPONSES_ENDPOINT,
                headers={
                    "Authorization": f"Bearer {credential}",
                    "Content-Type": "application/json",
                },
                content=body,
            )
            raw, failure = self._send(client, request)
        except Exception:  # noqa: BLE001 - sanitize construction/cleanup boundaries
            failure = ProviderPortError
            raw = b""
        finally:
            request = None
            credential = ""
            body = b""
            if client is not None:
                try:
                    client.close()
                except Exception:  # noqa: BLE001 - never expose cleanup diagnostics
                    if failure is None:
                        failure = ProviderPortError
                        raw = b""
            client = None
        return raw, failure

    def _send(
        self,
        client: httpx.Client,
        request: httpx.Request,
    ) -> tuple[bytes, type[ProviderPortError] | None]:
        started = self._monotonic()
        failure: type[ProviderPortError] | None = None
        raw = bytearray()
        response: httpx.Response | None = None
        try:
            response = client.send(request, stream=True, follow_redirects=False)
            if response.status_code >= 300:
                failure = (
                    ProviderUnavailableError
                    if response.status_code in {408, 409, 429}
                    or response.status_code >= 500
                    else ProviderPortError
                )
            else:
                for chunk in response.iter_bytes():
                    if self._monotonic() - started > self._policy.deadline_seconds:
                        failure = ProviderTimeoutError
                        break
                    if len(raw) + len(chunk) > self._policy.max_response_bytes:
                        failure = ProviderUnavailableError
                        break
                    raw.extend(chunk)
        except httpx.TimeoutException:
            failure = ProviderTimeoutError
        except httpx.RequestError:
            failure = ProviderUnavailableError
        except Exception:  # noqa: BLE001 - sanitize untrusted transport failures
            failure = ProviderPortError
        finally:
            if response is not None:
                try:
                    response.close()
                except Exception:  # noqa: BLE001 - sanitize response cleanup
                    if failure is None:
                        failure = ProviderPortError
                        raw.clear()
            response = None
            request = None
        if failure is not None:
            raw.clear()
            return b"", failure
        if self._monotonic() - started > self._policy.deadline_seconds:
            raw.clear()
            return b"", ProviderTimeoutError
        return bytes(raw), None

    def _decode(
        self,
        raw: bytes,
    ) -> tuple[JSONValue | None, type[ProviderPortError] | None]:
        response_value: object | None = None
        candidate_text: str | None = None
        try:
            response_value = self._decode_json(raw)
            candidate_text = self._candidate_text(response_value)
            candidate = self._decode_json(candidate_text)
        except ProviderUnavailableError:
            return None, ProviderUnavailableError
        except Exception:  # noqa: BLE001 - sanitize decoder/provider payload failures
            return None, ProviderPortError
        finally:
            response_value = None
            candidate_text = None
        return candidate, None

    def _prepare(self, request: TrustedProviderRequest) -> bytes:
        policy = self._policy
        now = self._utc_now()
        pricing = self._valid_pricing(policy, now)
        if pricing is None:
            raise ProviderPortError
        input_tokens = self._input_token_estimator(request)
        if type(input_tokens) is not int or not 0 <= input_tokens <= policy.max_input_tokens:
            raise ProviderPortError
        estimated_cost = (
            input_tokens * pricing.input_usd_per_million_tokens
            + policy.max_output_tokens * pricing.output_usd_per_million_tokens
        ) / 1_000_000
        if not math.isfinite(estimated_cost) or estimated_cost > policy.max_estimated_cost_usd:
            raise ProviderPortError
        provider_input = json.dumps(
            {
                "schema_version": request.schema_version,
                "output_schema_version": request.output_schema_version,
                "analysis_output_id": request.analysis_output_id,
                "analysis_input_id": request.analysis_input_id,
                "snapshot_id": request.snapshot_id,
                "evidence_digest": request.evidence_digest,
                "purpose": request.purpose,
                "untrusted_evidence_json": request.untrusted_evidence_json,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        body = json.dumps(
            {
                "model": policy.model_id,
                "instructions": "\n".join(request.trusted_instructions),
                "input": provider_input,
                "max_output_tokens": policy.max_output_tokens,
                "service_tier": "default",
                "prompt_cache_options": {"mode": "explicit"},
                "store": False,
                "stream": False,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(body) > policy.max_request_bytes:
            raise ProviderPortError
        return body

    @staticmethod
    def _valid_pricing(
        policy: OpenAIAdapterPolicy,
        now: datetime,
    ) -> ProviderPricingRecord | None:
        positive_ints = (
            policy.max_request_bytes,
            policy.max_response_bytes,
            policy.max_input_tokens,
            policy.max_output_tokens,
        )
        positive_numbers = (
            policy.connect_timeout_seconds,
            policy.read_timeout_seconds,
            policy.deadline_seconds,
            policy.max_estimated_cost_usd,
        )
        if not (
            policy.enabled is True
            and type(policy.model_id) is str
            and bool(policy.model_id)
            and type(policy.approved_model_ids) is frozenset
            and all(type(item) is str and bool(item) for item in policy.approved_model_ids)
            and policy.model_id in policy.approved_model_ids
            and type(policy.pricing_reference_id) is str
            and bool(policy.pricing_reference_id)
            and all(type(value) is int and value > 0 for value in positive_ints)
            and all(type(value) in {int, float} and math.isfinite(value) and value > 0 for value in positive_numbers)
            and policy.connect_timeout_seconds <= 5.0
            and policy.read_timeout_seconds <= 45.0
            and policy.deadline_seconds <= 60.0
            and policy.max_request_bytes <= 65_536
            and policy.max_response_bytes <= 131_072
            and policy.max_input_tokens <= 16_384
            and policy.max_output_tokens <= 4_096
            and policy.max_estimated_cost_usd <= 0.12
            and type(now) is datetime
            and now.tzinfo is not None
        ):
            return None
        pricing = resolve_authoritative_pricing(
            provider_id=_PROVIDER_ID,
            model_id=policy.model_id,
            service_tier="default",
            reference_id=policy.pricing_reference_id,
            now=now,
        )
        if pricing is None:
            return None
        return pricing

    @staticmethod
    def _candidate_text(response_value: object) -> str:
        if type(response_value) is not dict:
            raise ProviderPortError
        output = response_value.get("output")
        if type(output) is not list:
            raise ProviderUnavailableError
        texts: list[str] = []
        for item in output:
            if type(item) is not dict or item.get("type") != "message":
                continue
            content = item.get("content")
            if type(content) is not list:
                continue
            for part in content:
                if type(part) is dict and part.get("type") == "output_text":
                    text = part.get("text")
                    if type(text) is str:
                        texts.append(text)
        if len(texts) != 1:
            raise ProviderUnavailableError
        return texts[0]

    @staticmethod
    def _decode_json(value: bytes | str) -> JSONValue:
        def reject_constant(_value: str) -> None:
            raise ValueError

        def unique_object(pairs: list[tuple[str, JSONValue]]) -> dict[str, JSONValue]:
            result: dict[str, JSONValue] = {}
            for key, item in pairs:
                if key in result:
                    raise ValueError
                result[key] = item
            return result

        return json.loads(value, parse_constant=reject_constant, object_pairs_hook=unique_object)

    @staticmethod
    def _raise_clean(error_type: type[ProviderPortError]) -> None:
        raise error_type from None
