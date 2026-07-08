# Sprint 10 - Architecture Decisions

## 1. Alerting is EventBus subscribers, not new call sites in the request path
`atlas/alerting.py`'s two subscribers (`alert_on_forward_failure`,
`ClaudeFailureTracker.record`) register on the EventBus exactly the way
`atlas/events/subscribers.py::log_event` already does - registered in `atlas/main.py`'s
lifespan, independent of the webhook/AI code that publishes the events they react to.
No call site in `atlas/api/v1/webhook.py` or `atlas/ai.py` needed to change at all;
they already published `TRADE_ENTRY_FORWARD_FAILED`/`AI_ENTRY_SCORED`/etc. events since
Sprint 1/6. This is the exact "future subscribers register the same way" extension
point that module's own docstring predicted.

## 2. Alert delivery is fire-and-forget via `asyncio.create_task`, not awaited
`EventBus.publish()` awaits every subscriber directly (`asyncio.gather(...)`), and
`publish()` itself sits on the response-critical path in `atlas/api/v1/webhook.py`
(`await event_bus.publish(TRADE_ENTRY_FORWARD_FAILED, ...)` happens before the webhook
response is returned). If `alert_on_forward_failure` awaited the actual HTTP POST to
`ALERT_WEBHOOK_URL`, a slow or unreachable alerting endpoint would delay every webhook
response - the exact class of problem this whole codebase has been careful to avoid
for AI/Claude calls since Sprint 1. `send_alert()` schedules `_post_alert()` via
`asyncio.create_task` and returns immediately; the subscriber that calls it returns
just as fast. This was a genuine design constraint, not a stylistic choice - discovered
by tracing `publish()`'s actual call graph before writing `alerting.py`, not assumed.

## 3. One unified Claude-failure streak, not three per-event-type counters
`ClaudeFailureTracker` tracks consecutive failures across `AI_ENTRY_SCORED`,
`AI_TRADE_REVIEWED`, and `AI_REPORT_GENERATED` combined, subscribed to all three with
the same instance/method. The operational question an alert exists to answer ("is
something wrong with our Claude integration right now") doesn't depend on which
specific AI pass happened to fail - a real Anthropic outage would likely affect all
three simultaneously anyway, and three separate counters would either triple-alert for
one real outage or require deduplication logic that a single shared counter gets for
free.

## 4. Alerts fire on a threshold, and once more on recovery
Per-failure alerting was deliberately rejected for Claude (unlike PickMyTrade, where
every failure alerts - see decision #5): every AI module's own design already treats a
single Claude failure as expected and tolerated (that's the entire premise of "AI is
advisory only"). Alerting on every transient failure would make the alert channel
noise, not signal. `CLAUDE_FAILURE_ALERT_THRESHOLD` (default 3) sets how many
*consecutive* failures constitute "something is actually wrong." A recovery alert
fires once the streak resets after having crossed that threshold - deliberately not
after every success, and not at all if the streak never crossed the threshold in the
first place (see `test_tracker_success_before_threshold_sends_no_alert_at_all`) - so
the alert channel is a genuine two-way signal (broken → fixed), not a one-way stream of
bad news with no resolution.

## 5. PickMyTrade failures alert on every occurrence, no debouncing
Unlike Claude, PMT forward failures get no threshold/streak logic - one alert per
failure. This asymmetry is deliberate: PMT failures are rare at this strategy's actual
trade volume (a handful of signals a day, per every sprint's own "generous scan limit"
comments), and each one represents a specific missed trade that needs a specific human
response (see `docs/sprint10/deployment-runbook.md`'s incident response section) -
there's no meaningful "streak" concept the way there is for a degraded third-party API
that recovers over minutes.

## 6. Structured JSON logging: production only, not the local dev harness
`atlas/logging_config.py::configure_logging()` is called from `atlas/main.py` (the
real entrypoint) but deliberately not from `scripts/dev_seed_server.py`, which keeps
Sprint 1's plain-text `logging.basicConfig` format. A person tailing a local terminal
during development is better served by human-readable text; a log aggregator reading
Railway's log stream is better served by one JSON object per line with real,
independently-searchable fields. Two different consumers, two different formats,
matching the same "atlas.main is production, dev_seed_server is a local harness"
distinction Sprint 9 already established for authentication.

## 7. `GET /health` stays lightweight; `GET /status` remains the rich summary
Sprint 10 only adds `uptime_seconds`/`started_at` to `/health`. The richer
connectivity summary (TradingView/PickMyTrade/Claude last-seen timestamps) already
exists at `GET /status` (Sprint 2), whose own module docstring already draws this
exact distinction: `/health` answers "is this process up and can it reach the
database" (an infra health-check concern, deliberately public, deliberately minimal);
`/status` answers "who has this process actually heard from recently" (an application
concern, behind the Sprint 9 API key, richer). Duplicating `/status`'s logic into
`/health` would create two endpoints answering the same question with a chance to
drift out of sync - adding two narrow fields to the existing lightweight endpoint was
the smaller, more correct change.

## 8. Coverage threshold set from a measured baseline, not a round number
`--cov-fail-under=80` in `.github/workflows/ci.yml` was chosen after actually running
`pytest --cov=atlas` locally (87% today) and picking a floor with real margin below
it - not an arbitrary "80 sounds reasonable" guess. The gap between 80 and the
measured 87 is deliberate headroom: `atlas/repositories/postgres.py` (21%) and
`atlas/db.py` (40%) are legitimately low in *this* measurement because their real
coverage lives in `tests/integration/`, gated behind a real Postgres connection this
local measurement didn't have - CI's `backend-tests` job runs integration tests
separately (see decision #9) but does not fold their coverage into this same number
(a second `pytest --no-cov` invocation), so the CI-measured percentage should closely
match this local one. The threshold protects against real regressions without being
so tight that routine, low-risk changes spuriously fail the build.

## 9. CI runs a real Postgres service container for integration tests
`.github/workflows/ci.yml`'s `backend-tests` job spins up a `postgres:16` service
container and runs `tests/integration/` against it with `TEST_DATABASE_URL` set, in
addition to the in-memory unit suite. This directly closes a specific Sprint 8 audit
finding: "the single most important correctness guarantee in this system - two
simultaneous webhook deliveries can never double-order - has never actually been
executed in this project's development history," because `TEST_DATABASE_URL` was
never set in any sandbox this project has been developed in. As of this sprint, it
runs on every push/PR, not just when a developer happens to have a local Postgres.
