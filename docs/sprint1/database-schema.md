# Sprint 1 - Database Schema

## `trades`
One row per trade, updated across its lifecycle (entry -> price updates -> exit). Identical
column set to the Sprint 0 SQLite schema, so the data migration script is a straight copy.

| Column | Type | Notes |
|---|---|---|
| `id` | `BIGSERIAL PRIMARY KEY` | was `INTEGER PRIMARY KEY AUTOINCREMENT` in SQLite |
| `correlation_id` | `TEXT UNIQUE NOT NULL` | entry bar timestamp; the idempotency key |
| `received_at` | `TEXT NOT NULL` | ISO-8601 string, set server-side |
| `signal_time` | `TEXT` | from the Pine payload |
| `direction` | `TEXT` | `long` / `short` |
| `setup_tag` | `TEXT` | e.g. `BRK`, `RCL` |
| `symbol` | `TEXT` | e.g. `MNQU6` |
| `entry_price`, `sl`, `tp`, `atr`, `ema_distance_atr`, `regime_slope_pct` | `DOUBLE PRECISION` | were plain SQLite `REAL` |
| `sweep_age_bars` | `INTEGER` | |
| `session` | `TEXT` | `NY` / `London` / `Asia` |
| `status` | `TEXT NOT NULL DEFAULT 'open'` | `open` / `won` / `lost` |
| `current_price`, `unrealized_pnl` | `DOUBLE PRECISION` | set by `price_update` events |
| `last_update_at` | `TEXT` | |
| `exit_price`, `realized_pnl` | `DOUBLE PRECISION` | set by `exit` events |
| `closed_at` | `TEXT` | |
| `llm_model`, `llm_analysis`, `llm_error` | `TEXT` | set by the background Claude task |
| `pmt_forwarded` | `BOOLEAN NOT NULL DEFAULT FALSE` | was `INTEGER 0/1` in SQLite - the idempotency flag |
| `pmt_status_code` | `INTEGER` | HTTP status PickMyTrade returned, if any |
| `pmt_error` | `TEXT` | human-readable failure reason, if any |
| `raw_entry_payload` | `TEXT` | full JSON body received, for debugging |

Indexes: `idx_trades_correlation_id`, `idx_trades_received_at` (both existed in Sprint 0).

**What changed vs. Sprint 0, and why each change is safe:**
- `INTEGER` -> `BOOLEAN` for `pmt_forwarded`: psycopg returns native Python `bool`, which is
  what the application code already treated 0/1 as via truthiness checks - no logic change.
- `AUTOINCREMENT` -> `BIGSERIAL`: equivalent auto-incrementing behavior, room to grow well
  past SQLite's practical `INTEGER` range if trade volume ever gets large.
- `REAL` -> `DOUBLE PRECISION`: same IEEE 754 double-precision float, different name.
- Everything else is byte-for-byte the same column, same type family (`TEXT`), same
  nullability - this was a deliberate scope limit (see architecture-decisions.md #10).

## `schema_migrations`
New in Sprint 1. Tracks which migration files have been applied, so `migrations/runner.py`
can run idempotently on every startup without re-applying anything.

| Column | Type |
|---|---|
| `filename` | `TEXT PRIMARY KEY` |
| `applied_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` |

## Migration files
- `migrations/0001_init.sql` - creates `trades` and its indexes (see above).

Future migrations are added as `migrations/0002_....sql`, `0003_....sql`, etc. - see
`migrations/runner.py`'s docstring for the ordering/idempotency rules.
