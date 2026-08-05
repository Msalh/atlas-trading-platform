"""Default-disabled OpenAI transport adapter for offline Phase 18E qualification."""

from __future__ import annotations

import json
import math
import time
from collections.abc import Callable, Collection
from dataclasses import dataclass
from typing import Protocol

import httpx

from .errors import ProviderPortError, ProviderTimeoutError, ProviderUnavailableError
from .models import JSONValue, TrustedProviderRequest

_RESPONSES_ENDPOINT = "https://api.openai.com/v1/responses"


class InputTokenEstimator(Protocol):
    def __call__(self, request: TrustedProviderRequest) -> int: ...


class CredentialProvider(Protocol):
    def __call__(self) -> str: ...


@dataclass(frozen=True, slots=True)
class OpenAIAdapterPolicy:
    model_id: str
    approved_model_ids: Collection[str]
    enabled: bool = False
    max_request_bytes: int = 65_536
    max_response_bytes: int = 131_072
    max_input_tokens: int = 16_384
    max_output_tokens: int = 4_096
    connect_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 45.0
    deadline_seconds: float = 60.0
    max_estimated_cost_usd: float = 0.12
    input_usd_per_million_tokens: float = 0.0
    output_usd_per_million_tokens: float = 0.0
    pricing_verified: bool = False


class OpenAIProviderAdapter:
    """Perform one bounded Responses API operation and return untrusted JSON."""

    def __init__(
        self,
        *,
        client: httpx.Client,
        credential_provider: CredentialProvider,
        input_token_estimator: InputTokenEstimator,
        policy: OpenAIAdapterPolicy,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = client
        self._credential_provider = credential_provider
        self._input_token_estimator = input_token_estimator
        self._policy = policy
        self._monotonic = monotonic

    def invoke(self, request: TrustedProviderRequest) -> JSONValue:
        http_request = self._build_http_request(request)
        del request
        if http_request is None:
            self._raise_internal()

        raw, failure = self._send(http_request)
        http_request = None
        if failure is not None:
            self._raise_clean(failure)
        candidate, decode_failure = self._decode(raw)
        raw = b""
        if decode_failure is not None:
            self._raise_clean(decode_failure)
        return candidate

    def _build_http_request(
        self,
        request: TrustedProviderRequest,
    ) -> httpx.Request | None:
        body = b""
        credential: str | None = None
        http_request: httpx.Request | None = None
        try:
            body, _input_tokens = self._prepare(request)
            credential = self._credential_provider()
            if type(credential) is not str or not credential:
                raise ProviderPortError
            http_request = self._client.build_request(
                "POST",
                _RESPONSES_ENDPOINT,
                headers={
                    "Authorization": f"Bearer {credential}",
                    "Content-Type": "application/json",
                },
                content=body,
                extensions={
                    "timeout": {
                        "connect": self._policy.connect_timeout_seconds,
                        "read": self._policy.read_timeout_seconds,
                        "write": self._policy.read_timeout_seconds,
                        "pool": self._policy.connect_timeout_seconds,
                    }
                },
            )
        except Exception:  # noqa: BLE001 - fail closed across injected boundaries
            http_request = None
        finally:
            body = b""
            credential = None
        return http_request

    def _send(
        self,
        http_request: httpx.Request,
    ) -> tuple[bytes, type[ProviderPortError] | None]:
        started = self._monotonic()
        failure: type[ProviderPortError] | None = None
        raw = bytearray()
        response: httpx.Response | None = None
        try:
            response = self._client.send(
                http_request,
                stream=True,
                follow_redirects=False,
            )
            if response.status_code >= 300:
                failure = (
                    ProviderUnavailableError
                    if response.status_code in {408, 409, 429} or response.status_code >= 500
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
                response.close()
            response = None
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

    def _prepare(self, request: TrustedProviderRequest) -> tuple[bytes, int]:
        policy = self._policy
        if not self._valid_policy(policy):
            raise ProviderPortError
        input_tokens = self._input_token_estimator(request)
        if type(input_tokens) is not int or not 0 <= input_tokens <= policy.max_input_tokens:
            raise ProviderPortError
        estimated_cost = (
            input_tokens * policy.input_usd_per_million_tokens
            + policy.max_output_tokens * policy.output_usd_per_million_tokens
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
                "store": False,
                "stream": False,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(body) > policy.max_request_bytes:
            raise ProviderPortError
        return body, input_tokens

    @staticmethod
    def _valid_policy(policy: OpenAIAdapterPolicy) -> bool:
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
            policy.input_usd_per_million_tokens,
            policy.output_usd_per_million_tokens,
        )
        return (
            policy.enabled is True
            and type(policy.model_id) is str
            and bool(policy.model_id)
            and not isinstance(policy.approved_model_ids, (str, bytes))
            and all(
                type(model_id) is str and bool(model_id)
                for model_id in policy.approved_model_ids
            )
            and policy.model_id in policy.approved_model_ids
            and all(type(value) is int and value > 0 for value in positive_ints)
            and all(
                type(value) in {int, float} and math.isfinite(value) and value > 0
                for value in positive_numbers
            )
            and policy.connect_timeout_seconds <= 5.0
            and policy.read_timeout_seconds <= 45.0
            and policy.deadline_seconds <= 60.0
            and policy.max_request_bytes <= 65_536
            and policy.max_response_bytes <= 131_072
            and policy.max_input_tokens <= 16_384
            and policy.max_output_tokens <= 4_096
            and policy.max_estimated_cost_usd <= 0.12
            and policy.pricing_verified is True
        )

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

        return json.loads(
            value,
            parse_constant=reject_constant,
            object_pairs_hook=unique_object,
        )

    @staticmethod
    def _raise_clean(error_type: type[ProviderPortError]) -> None:
        raise error_type from None

    @classmethod
    def _raise_internal(cls) -> None:
        cls._raise_clean(ProviderPortError)
