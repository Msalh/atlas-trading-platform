# Sprint 2 - API Contracts Addendum

New read-only endpoints added this sprint, all under `/api/v1/` only (no legacy
unversioned path - nothing outside the new frontend depends on these yet). See
`docs/sprint1/api-contracts.md` for the untouched `/webhook`, `/health`, `/` contracts.

## `GET /api/v1/trades/current`
```json
{ "open": true, "trade": { /* full trade row, see below */ } }
```
`trade` is `null` when `open` is `false`.

## `GET /api/v1/trades?limit=50&status=open`
- `limit`: 1-200, default 50.
- `status`: optional, one of `open` / `won` / `lost`. Invalid value -> `400`.
```json
{ "count": 2, "trades": [ { /* trade row */ }, ... ] }
```
Most recent first (`ORDER BY id DESC`).

## `GET /api/v1/trades/{correlation_id}`
`404` if no trade exists for that id. Otherwise:
```json
{
  "trade": { /* full trade row */ },
  "timeline": [
    { "type": "entry_received", "at": "...", "direction": "long", "setup_tag": "BRK", "entry_price": 100, "sl": 90, "tp": 120 },
    { "type": "pmt_forwarded", "at": "...", "status_code": 200 },
    { "type": "ai_analysis", "at": null, "analysis": "...", "error": null },
    { "type": "price_update", "at": "...", "current_price": 105, "unrealized_pnl": 500, "note": "latest known price update, not a full history" },
    { "type": "exit", "at": "...", "status": "won", "exit_price": 120, "realized_pnl": 2000 }
  ]
}
```
`timeline` entries are only included for stages the trade has actually reached (a still-open
trade won't have an `exit` entry; a trade whose forward never failed won't have both
`pmt_forwarded` and `pmt_forward_failed`). `ai_analysis.at` is always `null` - see
architecture-decisions.md #2/#6 for why (no per-analysis timestamp is stored yet).

## `GET /api/v1/status`
```json
{
  "database": { "ok": true, "detail": "ok" },
  "tradingview": { "last_webhook_at": "...|null", "last_webhook_type": "trade.entry.received|trade.price_updated|trade.exit|null" },
  "pickmytrade": { "configured": true, "last_forward_at": "...|null", "last_forward_ok": true, "last_error": null },
  "claude": { "configured": true, "last_analysis_at": "...|null", "last_error": null }
}
```
Everything except `database` resets to "nothing seen yet" on every process restart - this is
answering "what has this running process observed," not querying history (see
architecture-decisions.md #3).

## `GET /api/v1/stats/today`
```json
{
  "date_utc": "2026-07-07",
  "trades_entered_today": 3,
  "trades_closed_today": 2,
  "wins_today": 1,
  "losses_today": 1,
  "realized_pnl_today": 300,
  "pmt_forward_failures_today": 0,
  "open_position": { "correlation_id": "...|null", "risk_points": 40.0, "reward_points": 100.0 }
}
```
`risk_points`/`reward_points` are in price points, not dollars (no contract multiplier is
persisted - see `atlas/api/v1/stats.py`'s docstring).

## Trade row shape (used throughout the above)
Identical to the `trades` table columns (`docs/sprint1/database-schema.md`) - returned
as-is, no field renaming, no computed fields added at the row level (computed values like
timeline/stats live in their own response fields, not mixed into the row).

## CORS
The API now sends `Access-Control-Allow-Origin` for GET requests from origins listed in the
`FRONTEND_ORIGINS` environment variable (comma-separated; defaults to
`http://localhost:3000`). TradingView's webhook and PickMyTrade's relay call the API
server-to-server and are unaffected by CORS either way.
