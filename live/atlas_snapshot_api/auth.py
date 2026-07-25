"""Constant-time authentication with separate capture and read authority."""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from enum import Enum

from fastapi import HTTPException, Request


class SnapshotRole(str, Enum):
    READER = "reader"
    OPERATOR = "operator"


@dataclass(frozen=True, slots=True)
class SnapshotPrincipal:
    role: SnapshotRole


@dataclass(frozen=True, slots=True)
class SnapshotAuthConfig:
    reader_token: str
    operator_token: str

    def validate(self) -> None:
        if (
            not self.reader_token
            or not self.operator_token
            or self.reader_token == self.operator_token
        ):
            raise ValueError("distinct reader and operator tokens are required")


def _bearer(request: Request) -> str | None:
    authorization = request.headers.get("Authorization")
    if not authorization:
        return None
    scheme, separator, token = authorization.partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not token:
        return None
    return token


def authenticate(request: Request) -> SnapshotPrincipal:
    token = _bearer(request)
    config: SnapshotAuthConfig = request.app.state.snapshot_auth
    if token and hmac.compare_digest(token, config.operator_token):
        return SnapshotPrincipal(SnapshotRole.OPERATOR)
    if token and hmac.compare_digest(token, config.reader_token):
        return SnapshotPrincipal(SnapshotRole.READER)
    raise HTTPException(status_code=401, detail="missing or invalid credentials")


def require_reader(request: Request) -> SnapshotPrincipal:
    return authenticate(request)


def require_operator(request: Request) -> SnapshotPrincipal:
    principal = authenticate(request)
    if principal.role is not SnapshotRole.OPERATOR:
        raise HTTPException(status_code=403, detail="capture authority required")
    return principal
