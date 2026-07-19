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

# Sprint 6 - AI Copilot. Replaces the old single TRADE_AI_ANALYZED event (Sprints 1-5):
# there are now three distinct AI passes instead of one, so they get distinct event
# types - see atlas/ai.py.
AI_ENTRY_SCORED = "ai.entry_scored"
AI_TRADE_REVIEWED = "ai.trade_reviewed"
AI_REPORT_GENERATED = "ai.report_generated"

# Market Engine Sprint 7 - fired on every successful ingest (STORED or
# DUPLICATE; a duplicate still proves data is flowing, which is what
# staleness detection cares about) - see atlas/api/v1/market_state.py and
# atlas/monitoring.py. Adding it here is what makes SystemStatus track its
# last-seen time automatically, via the existing subscription loop below -
# no separate tracking mechanism needed.
MARKET_STATE_INGESTED = "market_state.ingested"

ALL = [
    TRADE_ENTRY_RECEIVED,
    TRADE_ENTRY_FORWARDED,
    TRADE_ENTRY_FORWARD_FAILED,
    TRADE_ENTRY_DUPLICATE,
    TRADE_PRICE_UPDATED,
    TRADE_EXIT,
    AI_ENTRY_SCORED,
    AI_TRADE_REVIEWED,
    AI_REPORT_GENERATED,
    MARKET_STATE_INGESTED,
]
