-- "quantity" (contracts) was always part of the webhook payload and already forwarded to
-- PickMyTrade (see PMT_FIELDS in atlas/services/pickmytrade.py) but was never persisted on
-- our own trades row. Sprint 4's position-sizing/exposure/unrealized-risk-in-dollars
-- calculations need it. Purely additive - does not change the TradingView payload contract,
-- only what we choose to store from a field that was already being sent.

ALTER TABLE trades ADD COLUMN IF NOT EXISTS quantity INTEGER;
