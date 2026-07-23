"""
FastAPI dependency providers. Routes declare
`repository: TradeRepository = Depends(get_repository)` instead of importing a
concrete repository/pool directly - this is what lets tests override these
dependencies with the in-memory test double via `app.dependency_overrides`, without
the route code ever knowing the difference.
"""
from typing import Optional

from fastapi import Request

from atlas.events.bus import EventBus
from atlas.market_engine.ports import MarketStateRepository
from atlas.repositories.base import TradeRepository
from atlas.research_deploy.startup_check import LedgerReadiness, LedgerStores
from atlas.research_export.startup_check import SnapshotsReadiness
from atlas.status import SystemStatus


def get_repository(request: Request) -> TradeRepository:
    return request.app.state.repository


def get_event_bus(request: Request) -> EventBus:
    return request.app.state.event_bus


def get_system_status(request: Request) -> SystemStatus:
    return request.app.state.system_status


def get_market_state_repository(request: Request) -> MarketStateRepository:
    return request.app.state.market_state_repository


def get_snapshots_readiness(request: Request) -> SnapshotsReadiness:
    return request.app.state.snapshots_readiness


def get_ledger_readiness(request: Request) -> LedgerReadiness:
    return request.app.state.ledger_readiness


def get_ledger_stores(request: Request) -> Optional[LedgerStores]:
    """None only in the rare case that check_ledger_storage() itself
    raised something unanticipated at startup (a bug in that function, not
    a bad directory - see atlas.main's lifespan) - callers must check
    get_ledger_readiness()'s own status before touching this, the same
    "check readiness before loading" discipline
    atlas/api/v1/research.py's _degraded_response() already established
    for snapshots."""
    return request.app.state.ledger_stores
