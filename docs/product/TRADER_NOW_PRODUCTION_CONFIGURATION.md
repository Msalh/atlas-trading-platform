# TraderNow production configuration

TraderNow uses the CME Globex equity-index electronic session in
`America/Chicago`: Sunday open at 17:00, daily 16:00–17:00 maintenance,
and Friday close at 16:00. The policy implementation is versioned by
`TRADER_NOW_CALENDAR_VERSION`.

Holiday and early-close exceptions are operator-maintained from the published
CME holiday schedule. `TRADER_NOW_HOLIDAYS_JSON` is an explicit JSON array of
fully closed local exchange dates. `TRADER_NOW_EARLY_CLOSES_JSON` maps local
exchange dates to `HH:MM` closes. A date cannot appear in both.

## Manual MNQ rollover

1. Confirm the exact MNQ contract symbol already persisted in
   `market_state_events.symbol`.
2. Stop ingestion from mixing old and new contract identities.
3. Set `TRADER_NOW_CONTRACT_SYMBOL` to that exact persisted symbol.
4. Set a new, immutable `TRADER_NOW_CONTRACT_RESOLUTION_VERSION`.
5. Set `TRADER_NOW_CONTRACT_EFFECTIVE_DATE` to the operational effective date.
6. Review the current CME holiday schedule; update both exception JSON values
   and increment `TRADER_NOW_CALENDAR_VERSION` when it changes.
7. Restart the backend and verify TraderNow identity, latest closed timestamp,
   freshness, and an unavailable/no-data response before treating it as ready.

There is no automatic rollover and no fallback contract. Missing, malformed,
partial, or unsupported production configuration fails startup.

## Read-only database requirement

The TraderNow request path executes one bounded `SELECT` from
`market_state_events`, using the existing `(symbol, timeframe, occurred_at)`
index and a 288-row limit. A future dedicated analysis role needs `CONNECT` on
the database, `USAGE` on the containing schema, and `SELECT` on
`market_state_events`; it does not need table write, sequence, migration,
trade, AI, research-ledger, or broker permissions.
