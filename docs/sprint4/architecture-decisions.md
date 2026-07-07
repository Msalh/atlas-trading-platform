# Sprint 4 - Architecture Decisions

## 1. Env-var account config, not an `accounts` table - for now
The original V2 architecture sketch proposed an `accounts` table for multi-account support.
Sprint 4 does not add it. There is exactly one funded account and one instrument (MNQ) in
practice today - a table exists to be *keyed on*, and there's nothing to key a second row on
yet. Adding one now would be schema speculation ahead of an actual need, the same judgment
call Sprint 1 made about multi-tenant auth. `ACCOUNT_STARTING_BALANCE`,
`ACCOUNT_DAILY_LOSS_LIMIT`, `ACCOUNT_TRAILING_DRAWDOWN_LIMIT`, `ACCOUNT_MAX_CONTRACTS`,
`ACCOUNT_POINT_VALUE` are environment variables, matching every other piece of deployment
config in this codebase (`WEBHOOK_SECRET`, `PICKMYTRADE_WEBHOOK_URL`, etc.). Revisit as a
real table in Sprint 8 (broker expansion) or whenever a second account actually exists.

## 2. `account_configured` - a loud, explicit "these numbers might be fake" flag
Because this is real-money risk display, not a cosmetic feature, defaulting silently to
round numbers (`$50,000` starting balance, `$1,000` daily loss limit) would be actively
misleading if someone glanced at the Account page assuming it reflected their real funded
account. `Settings.account_configured` checks whether the four required env vars were
*explicitly set* (not whether their values happen to differ from the defaults - a real
account could legitimately have `$50,000` as its actual starting balance). The frontend
surfaces this as a persistent amber banner on `/account`, shown *alongside* the kill-switch
state, not instead of it (see #5 - this was a real bug caught during this sprint's own
verification, not designed correctly the first time).

## 3. `quantity` added to `trades`, nothing else changed about the payload
Position sizing, exposure, and dollar-denominated risk/reward all need contract count.
`quantity` was already part of every webhook payload (used to forward to PickMyTrade) but
was never persisted. Sprint 4 adds one nullable column
(`migrations/0002_add_quantity.sql`) and stores a field that was already being sent -
`atlas/api/v1/webhook.py` and the TradingView/PickMyTrade payload contracts are completely
untouched. Old rows (migrated from Sprint 0, or any trade that predates this migration) have
`quantity = NULL`; every risk calculation that needs it is written to handle `None` without
crashing (see `atlas/risk.py::_build_open_position_risk`).

## 4. Risk math lives in pure functions, exactly like `build_timeline`
`atlas/risk.py::compute_risk_snapshot` takes a list of trade dicts and scalar settings,
returns dataclasses, touches no database and no FastAPI request. `atlas/api/v1/risk.py` is
a thin fetch-and-serialize wrapper. This is the same shape as Sprint 2's
`atlas/api/v1/trades.py::build_timeline` and exists for the same reason: the actual logic
(balance/high-water-mark/drawdown/kill-switch math) is fully unit-testable with hand-built
trade lists and no test infrastructure, independent of whether the wiring around it (the
route, the repository call) is correct.

## 5. Kill switch is a computed *fact*, not a stored one, and never enforced
`KillSwitchStatus.enforced` is hardcoded `False` - there is no code path in this sprint that
can set it to anything else, by construction. `should_trigger`/`reasons` are recomputed from
scratch on every request from the current trade history and settings - nothing is written to
the database, nothing persists across a value that could get stuck stale. The webhook/relay
path (`atlas/api/v1/webhook.py`) does not import `atlas/risk.py` at all - there is no code
path by which this sprint's work could affect order execution, satisfying "do not block
order execution / do not enforce risk rules" by the absence of a connection, not by
discipline alone.

**Bug caught during this sprint's own verification**: the frontend's `KillSwitchBanner`
originally returned early when `account_configured` was false, which meant an *actual* kill
switch trigger (e.g. daily loss breached) was silently hidden behind the "not configured"
notice - exactly the kind of thing this sprint exists to make impossible to miss. Fixed to
show both states together (the config warning is about trusting the numbers; the kill switch
state is what the numbers currently say, trustworthy or not) and re-verified visually.

## 6. Daily loss and trailing drawdown are computed from this account's own realized P&L only
`current_balance = starting_balance + sum(realized_pnl of all closed trades, in the order
they closed)`. There is no broker/prop-firm balance feed integration - if the real account
balance ever diverges from this (external deposits, fees, other activity), this will be
wrong until that integration exists. Stated in `atlas/risk.py`'s module docstring rather than
assumed silently. "Today" is the UTC calendar day, the same simplification `stats.py` already
made and documented in Sprint 2 - not a real trading-session boundary.

## 7. Exposure warnings are separate from kill-switch reasons
A position exceeding `max_contracts` is shown as its own warning badge on the Exposure card,
not folded into `kill_switch.reasons`. Reasoning: the kill switch concept (in real funded
accounts) means "you must stop trading" - that's daily loss and trailing drawdown, the two
things that actually end an account. Oversized position sizing is a different, correctable-
mid-trade concern. Conflating them would make the kill switch banner fire for a milder
problem than what "kill switch" should mean.
