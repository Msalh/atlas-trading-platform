"""
Built-in event subscribers registered at application startup (see atlas/main.py). The
logging subscriber is a real, always-on production subscriber, not a placeholder - it
is what makes every trade lifecycle event visible in Railway's log stream today.
Sprint 10's alerting subscribers (atlas/alerting.py) register the same way,
independent of this one and of the webhook/execution code that publishes events.
"""
import logging
from typing import Any

logger = logging.getLogger("atlas.trade_events")


async def log_event(event_type: str, payload: dict[str, Any]) -> None:
    """Sprint 10: event_type/payload are passed via `extra` rather than pre-formatted
    into the message string, so atlas/logging_config.py's JSON formatter emits them as
    real, independently-searchable top-level fields instead of a JSON blob nested
    inside `message`."""
    logger.info(event_type, extra={"event_type": event_type, "payload": payload})
