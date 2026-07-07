"""
Event type name constants published on the EventBus - the single source of truth for
what a subscriber can listen for. Add a new constant here before publishing or
subscribing to a new event type; never use a bare string literal at the call site.
"""

TRADE_ENTRY_RECEIVED = "trade.entry.received"
TRADE_ENTRY_FORWARDED = "trade.entry.forwarded"
TRADE_ENTRY_FORWARD_FAILED = "trade.entry.forward_failed"
TRADE_ENTRY_DUPLICATE = "trade.entry.duplicate"
TRADE_PRICE_UPDATED = "trade.price_updated"
TRADE_EXIT = "trade.exit"
TRADE_AI_ANALYZED = "trade.ai_analyzed"

ALL = [
    TRADE_ENTRY_RECEIVED,
    TRADE_ENTRY_FORWARDED,
    TRADE_ENTRY_FORWARD_FAILED,
    TRADE_ENTRY_DUPLICATE,
    TRADE_PRICE_UPDATED,
    TRADE_EXIT,
    TRADE_AI_ANALYZED,
]
