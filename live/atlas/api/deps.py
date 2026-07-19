"""
FastAPI dependency providers. Routes declare
`repository: TradeRepository = Depends(get_repository)` instead of importing a
concrete repository/pool directly - this is what lets tests override these
dependencies with the in-memory test double via `app.dependency_overrides`, without
the route code ever knowing the difference.
"""
from fastapi import Request

from atlas.events.bus import EventBus
from atlas.market_engine.ports import MarketStateRepository
from atlas.repositories.base import TradeRepository
from atlas.status import SystemStatus


def get_repository(request: Request) -> TradeRepository:
    return request.app.state.repository


def get_event_bus(request: Request) -> EventBus:
    return request.app.state.event_bus


def get_system_status(request: Request) -> SystemStatus:
    return request.app.state.system_status


def get_market_state_repository(request: Request) -> MarketStateRepository:
    return request.app.state.market_state_repository
