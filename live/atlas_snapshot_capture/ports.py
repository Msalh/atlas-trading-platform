"""Application ports owned by the private capture service."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from .models import CaptureRequest


class TraderNowClient(Protocol):
    async def start(self) -> None: ...

    async def close(self) -> None: ...

    async def fetch_latest(
        self,
        request: CaptureRequest,
        *,
        correlation_id: str,
    ) -> Mapping[str, Any]: ...
