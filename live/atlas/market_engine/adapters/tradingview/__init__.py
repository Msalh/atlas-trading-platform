"""
The TradingView market-state adapter: wire_models.py validates the raw JSON
shape TradingView Pine sends; translator.py maps a validated wire payload into
the canonical MarketState. This is the first of what the architecture expects
to eventually be several adapters (Tradovate, Databento, ...) - a future one is
added as a new sibling package here, never by modifying this one or
market_engine.models.
"""
