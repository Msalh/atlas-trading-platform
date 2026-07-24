"""Dependencies shared only by TraderNow transport adapters."""

from fastapi import Request

from atlas.application import TraderNowApplication


def get_trader_now_application(request: Request) -> TraderNowApplication:
    return request.app.state.trader_now_application
