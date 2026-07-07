# Sprint 5 - Architecture Decisions

## 1. Three endpoints, not one - matching three distinct UI shapes
`/analytics/summary` (scalar cards), `/analytics/equity-curve` (time series), and
`/analytics/breakdown` (three grouped tables) are separate resources rather than one big
payload. Each maps to a genuinely different response shape the frontend consumes
differently (a handful of numbers vs. a chart-ready array vs. grouped aggregates) - this is
normal REST resource design, not a workaround for anything. All three still do their own
independent `list_recent(limit=SCAN_LIMIT)` fetch, same as `stats.py`/`risk.py` before them;
revisit if profiling ever shows that's actually a cost at this trade volume.

## 2. `risk_reward_points` promoted from private to shared
Average R-multiple needs the same "risk in points for this direction/entry/sl" calculation
Sprint 4's Risk Engine already had (as `atlas/risk.py::_risk_reward_points`). Renamed to
`risk_reward_points` (dropped the leading underscore) and imported directly into
`atlas/analytics.py`, rather than writing a second copy that could drift from the first.
Mechanical rename only - no behavior change, and Sprint 4's full test suite still passes
unmodified, confirming that.

## 3. Equity curve intentionally duplicates ~6 lines of Sprint 4's balance loop
`compute_equity_curve` recomputes the same running-balance/high-water-mark logic
`atlas/risk.py::compute_risk_snapshot` already has, rather than importing a shared helper.
Reasoning: `risk.py` only ever needed the *final* balance/peak; `analytics.py` needs the
*full series* at every point, a different return shape. Refactoring Sprint 4's
already-approved, tested code to serve a new caller mid-Sprint-5 was judged a worse trade
than ~6 duplicated lines, especially since the display-only Risk Engine's correctness is
safety-relevant (real funded account) and not worth touching without a concrete need. If a
third caller ever needs this exact loop, that's the point to extract a shared helper - not
before.

## 4. Every metric is closed-trades-only, attributed by `closed_at`
Open positions have no realized outcome yet, so none of Sprint 5's metrics (win rate,
profit factor, expectancy, equity curve, breakdowns) include them - consistent with how
Sprint 4's daily-loss tracking already attributes P&L to `closed_at`'s date, not
`received_at`'s. Stated in `atlas/analytics.py`'s module docstring, not assumed silently.

## 5. Average R excludes trades with incomplete risk data - and says so
A trade missing `quantity` (pre-Sprint-4 data) or with `entry_price`/`sl`/`tp` absent can't
have a dollar risk computed, so it's excluded from the `avg_r` average specifically - it
still counts fully toward every other metric (win rate, expectancy, equity curve).
`r_multiple_sample_size` is returned alongside `avg_r` so "average R across all your trades"
vs. "average R across the dna trades where we could actually compute it" is never
ambiguous to whoever's reading the number.

## 6. Chart library: Recharts, not TradingView Lightweight Charts
The original V2 architecture doc suggested Lightweight Charts for price-style panels and a
general React charting library (Recharts/visx) for analytics distributions. Sprint 5's
charts (equity curve, drawdown, breakdown bars) are all "basic charts" over pre-aggregated
data, not interactive price/candle charts needing time-axis panning/zooming - Recharts'
declarative JSX API is the better fit and is now the only charting dependency in the
frontend. Lightweight Charts remains the right choice *if* a future sprint (Replay Engine,
Sprint 7) needs true price/candle rendering - not added preemptively here.

## 7. SSE invalidates `["analytics"]` only on `trade.exit`
Unlike `["trades"]`/`["status"]`/`["risk"]` (invalidated on every `trade.*` event - see
Sprint 3/4's `live-updates.tsx`), analytics only changes when a trade actually closes
(entries and price updates don't touch closed-trade history). Narrower invalidation here
isn't a performance optimization at this trade volume - it's just accuracy: invalidating a
query that can't have changed would just be misleading busywork.

## 8. Seed data: a realistic-looking history was added deliberately, not organically
`scripts/dev_seed_server.py::_seed_analytics_history` adds 13 additional closed trades
spanning multiple sessions/setups/days specifically so the charts have enough shape to
evaluate visually - the 3 trades from Sprints 2-4's seed data would make an equity curve of
2 points, which doesn't exercise anything. Explicitly labeled in that function's docstring
as "not meant to resemble any specific real trading history" - it's a rendering fixture, not
a claim about strategy performance.
