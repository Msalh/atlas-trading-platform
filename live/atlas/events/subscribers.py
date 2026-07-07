"""
Built-in event subscribers registered at application startup (see atlas/main.py). The
logging subscriber is a real, always-on production subscriber, not a placeholder - it
is what makes every trade lifecycle event visible in Railway's log stream today.
Future subscribers (Discord, Telegram, Email - see the platform roadmap) register the
same way, independent of one another and of the webhook/execution code that publishes
events.
"""
import json
import logging
from typing import Any

logger = logging.getLogger("atlas.trade_events")


async def log_event(event_type: str, payload: dict[str, Any]) -> None:
    logger.info("%s %s", event_type, json.dumps(payload, default=str))
