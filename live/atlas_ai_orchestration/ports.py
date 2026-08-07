"""Injected, offline-testable ports used by Phase 18D."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from atlas_ai_analysis import GeneratorIdentity

from .models import JSONValue, TrustedProviderRequest


class IdentityFactory(Protocol):
    def __call__(self) -> str: ...


class UTCClock(Protocol):
    def __call__(self) -> str: ...


class TrustedPromptBuilder(Protocol):
    def build(self, analysis_input: Mapping[str, Any]) -> TrustedProviderRequest: ...


class CostPolicy(Protocol):
    def allows(self, request: TrustedProviderRequest) -> bool: ...


class ProviderPort(Protocol):
    @property
    def identity(self) -> GeneratorIdentity: ...

    def invoke(self, request: TrustedProviderRequest) -> JSONValue: ...
