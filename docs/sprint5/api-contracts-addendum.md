# Sprint 5 - API Contract Addendum

All three endpoints are read-only, no query params, no auth (matches every other
`/api/v1/*` read endpoint). All computed over closed trades only - see
`docs/sprint5/architecture-decisions.md` #4.

## `GET /api/v1/analytics/summary`
```json
{
  "total_trades": 15,
  "wins": 9,
  "losses": 6,
  "win_rate_pct": 60.0,
  "gross_profit": 3000.0,
  "gross_loss": 1280.0,
  "profit_factor": 2.34375,
  "expectancy": 114.67,
  "avg_win": 333.33,
  "avg_loss": -213.33,
  "avg_r": 0.4,
  "r_multiple_sample_size": 15
}
```
- `profit_factor` is `null` when there are no losing trades (undefined ratio, not
  infinity or a divide-by-zero error).
- `avg_win` is `null` with zero wins; `avg_loss` is `null` with zero losses. `avg_loss` is
  a **negative** number (matches the sign convention used everywhere else for realized
  P&L); `gross_loss` is a **positive magnitude** (used for the profit-factor ratio).
- `avg_r` is `null` if no closed trade had computable risk (see architecture-decisions.md
  #5); `r_multiple_sample_size` tells you how many trades actually contributed to it,
  which can be less than `total_trades`.
- `expectancy` is average realized P&L per closed trade, in dollars.

## `GET /api/v1/analytics/equity-curve`
```json
{
  "starting_balance": 50000.0,
  "points": [
    {
      "correlation_id": "seed-hist-0",
      "closed_at": "2026-06-23T15:00:00+00:00",
      "realized_pnl": 300.0,
      "equity": 50300.0,
      "high_water_mark": 50300.0,
      "drawdown": 0.0,
      "drawdown_pct": 0.0
    }
  ],
  "ending_equity": 51720.0,
  "max_drawdown": 480.0,
  "max_drawdown_pct": 2.0
}
```
`points` is one entry per closed trade, in chronological order by `closed_at`.
`starting_balance` is `settings.account_starting_balance` (the same Sprint 4 account
config) - if that's not configured for your real account yet, this curve isn't either (no
separate `configured` flag here; check `/api/v1/risk`'s `account_configured` for that,
since it's the same underlying setting). `drawdown`/`drawdown_pct` are the distance below
the running high-water mark at that point, always &ge; 0. `max_drawdown`/`max_drawdown_pct`
are the largest of those values across the whole series (the "worst" point, not
necessarily the last one).

## `GET /api/v1/analytics/breakdown`
```json
{
  "by_session": [
    {"key": "London", "total_trades": 5, "wins": 4, "losses": 1, "win_rate_pct": 80.0, "total_realized_pnl": 1340.0, "avg_realized_pnl": 268.0}
  ],
  "by_setup": [ /* same shape, keyed by setup_tag */ ],
  "by_weekday": [ /* same shape, keyed by weekday name */ ]
}
```
- `by_session`/`by_setup` groups use `"Unknown"` as the key for trades missing that field,
  and are sorted by `total_trades` descending (most active group first).
- `by_weekday` uses the trade's `closed_at` date (not `received_at`) and is sorted
  **Monday through Sunday**, not by count - a calendar-order read is more natural for "day
  of week" than an activity-ranked one. Missing/unparseable `closed_at` groups under
  `"Unknown"`.
