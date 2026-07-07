# Sprint 4 - API Contract Addendum

## `GET /api/v1/risk`
```json
{
  "account_configured": true,
  "starting_balance": 50000.0,
  "current_balance": 50400.0,
  "high_water_mark": 50400.0,

  "daily_loss_limit": 1000.0,
  "daily_realized_pnl": 400.0,
  "daily_loss_used": 0.0,
  "daily_loss_remaining": 1000.0,
  "daily_loss_limit_breached": false,

  "trailing_drawdown_limit": 2000.0,
  "trailing_stop_balance": 48400.0,
  "remaining_drawdown": 2000.0,
  "trailing_drawdown_breached": false,

  "max_contracts": 5,
  "point_value": 2.0,

  "open_position": {
    "correlation_id": "seed-open-1",
    "direction": "long",
    "quantity": 6,
    "entry_price": 21500.0,
    "sl": 21460.0,
    "tp": 21600.0,
    "current_price": 21538.25,
    "unrealized_pnl": 306.25,
    "risk_points": 40.0,
    "reward_points": 100.0,
    "risk_dollars": 480.0,
    "reward_dollars": 1200.0,
    "exposure_contracts": 6,
    "exposure_pct_of_max": 120.0,
    "exceeds_max_contracts": true
  },
  "kill_switch": {
    "should_trigger": false,
    "reasons": [],
    "enforced": false
  }
}
```
`open_position` is `null` when flat. Any numeric field on `open_position` can be `null` if
`quantity` was never recorded for that trade (pre-Sprint-4 data, or a payload that omitted
it) - `risk_dollars`/`reward_dollars`/`exposure_pct_of_max` specifically depend on it and
degrade to `null` rather than guessing.

**`kill_switch.enforced` is always `false`.** This is not a bug and will not change without
an explicit future sprint - see `docs/sprint4/architecture-decisions.md` #5. Nothing calls
this endpoint from `atlas/api/v1/webhook.py`; it has zero effect on order execution.

**`account_configured: false`** means `ACCOUNT_STARTING_BALANCE`, `ACCOUNT_DAILY_LOSS_LIMIT`,
`ACCOUNT_TRAILING_DRAWDOWN_LIMIT`, or `ACCOUNT_MAX_CONTRACTS` were not explicitly set as
environment variables - every number in the response is still computed and returned, just
against placeholder defaults. Treat the whole response as untrustworthy for a real account
until this is `true`.

No query params, no auth (matches every other `/api/v1/*` read endpoint).

## New field on existing trade rows
`quantity: number | null` now appears on every `Trade` object returned by
`/api/v1/trades/current`, `/api/v1/trades`, and `/api/v1/trades/{id}` (see Sprint 2's
addendum for those response shapes) - `null` for any trade recorded before this sprint's
migration.
