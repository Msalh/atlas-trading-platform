# Sprint 1 - API Contracts

Unchanged externally from Sprint 0 except for the addition of the `/api/v1/` prefix as an
alternate path. `/webhook`, `/health`, `/` continue to work exactly as before - nothing on
the TradingView side needs to change.

## `POST /webhook` (also `POST /api/v1/webhook`)

Request body (`application/json`), one of three shapes selected by `"type"` (defaults to
`"entry"` if omitted, for backward compatibility with the original Pine alert format):

### `type: "entry"`
```json
{
  "type": "entry",
  "correlation_id": "2026-07-07T17:35:00Z",
  "secret": "...",
  "symbol": "MNQU6",
  "strategy_name": "NQ RECLAIM NY LONG",
  "data": "BUY",
  "quantity": 12,
  "price": 30000,
  "tp": 30050,
  "sl": 29950,
  "token": "...",
  "direction": "long",
  "setup_tag": "BRK",
  "entry_price": 30000,
  "atr": 42.5,
  "ema_distance_atr": 0.8,
  "regime_slope_pct": 1.2,
  "sweep_age_bars": 6,
  "session": "NY",
  "signal_time": "2026-07-07T17:35:00Z"
}
```
Fields listed under `PMT_FIELDS` in `atlas/services/pickmytrade.py` are forwarded verbatim
to PickMyTrade; everything else is stored but not forwarded.

Responses:
| Status | Body | Meaning |
|---|---|---|
| 200 | `{"ok": true, "pmt_forwarded": true, "pmt_status_code": 200, "pmt_error": null}` | forwarded successfully |
| 207 | `{"ok": true, "pmt_forwarded": false, "pmt_status_code": null, "pmt_error": "..."}` | stored, forward failed/unconfigured |
| 208 | `{"ok": true, "duplicate_already_forwarded": true, "correlation_id": "..."}` | already forwarded previously, no-op |
| 400 | `{"ok": false, "error": "..."}` | invalid JSON / missing `correlation_id` |
| 401 | `{"ok": false, "error": "bad secret"}` | `secret` didn't match `WEBHOOK_SECRET` |
| 500 | `{"ok": false, "error": "db error: ..."}` | unexpected server/database error |

### `type: "price_update"`
```json
{
  "type": "price_update",
  "correlation_id": "2026-07-07T17:35:00Z",
  "secret": "...",
  "current_price": 30025,
  "unrealized_pnl": 150
}
```
Responses: `200 {"ok": true}` on match, `200 {"ok": true, "warning": "no trade found for correlation_id ..."}`
if no trade exists yet for that id (not an error - acknowledged so TradingView doesn't retry).

### `type: "exit"`
```json
{
  "type": "exit",
  "correlation_id": "2026-07-07T17:35:00Z",
  "secret": "...",
  "outcome": "WIN",
  "exit_price": 30050,
  "realized_pnl": 600
}
```
`outcome` other than the literal string `"WIN"` (case-insensitive) is recorded as `"lost"`.
Same response shape as `price_update`.

## `GET /health` (also `GET /api/v1/health`)
| Status | Body |
|---|---|
| 200 | `{"ok": true, "database": "ok"}` |
| 503 | `{"ok": false, "database": "error: ..."}` |

## `GET /`
Returns the HTML dashboard (`text/html`), auto-refreshing every 15 seconds, showing the
latest 100 trades. Unversioned - this is a browser-facing page, not an integration surface.
No request body; no auth beyond obscurity of the URL (see README's Notes section).
