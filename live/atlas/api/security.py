"""
API key authentication (Sprint 9). A single shared key, checked via constant-time
comparison, protects every route except the webhook (which has its own shared-secret
scheme matching TradingView's payload contract - see atlas/api/v1/webhook.py) and
GET /health (deliberately public: Railway's own health-check prober doesn't send
custom headers, and the response reveals nothing beyond "is the database reachable").

Applied at router-registration time in atlas/main.py via
`app.include_router(..., dependencies=[Depends(require_api_key)])`, not per-route -
one central list of which routers are protected, instead of relying on every route
function remembering to declare it individually.
"""
import hmac
from typing import Optional

from fastapi import Header, HTTPException, Query, Request

from atlas.config import settings


def _extract_bearer(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value:
        return None
    return value


def _check(token: Optional[str]) -> None:
    if not token or not settings.api_key or not hmac.compare_digest(token, settings.api_key):
        raise HTTPException(status_code=401, detail="missing or invalid API key")


def require_api_key(request: Request, authorization: Optional[str] = Header(default=None)) -> None:
    _check(_extract_bearer(authorization))


def require_api_key_for_stream(
    request: Request,
    authorization: Optional[str] = Header(default=None),
    api_key: Optional[str] = Query(default=None),
) -> None:
    """Identical check to require_api_key, but also accepts the key as a query
    parameter (`?api_key=...`). Browsers' native EventSource API cannot set custom
    request headers, so GET /api/v1/stream is the one endpoint that needs this
    fallback - see frontend/src/lib/live-updates.tsx."""
    _check(_extract_bearer(authorization) or api_key)
