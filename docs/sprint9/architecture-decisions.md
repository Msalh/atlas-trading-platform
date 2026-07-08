# Sprint 9 - Architecture Decisions

## 1. "Refuse to start unsafely" extended from DATABASE_URL to WEBHOOK_SECRET/API_KEY
`atlas/db.py::create_pool()` has always refused to start without `DATABASE_URL` rather
than silently falling back to nothing. `Settings.validate_for_startup()`
(`atlas/config.py`, called from `atlas/main.py`'s lifespan before `create_pool()`)
applies the exact same discipline to the two gaps the Sprint 8 audit found most
dangerous: a blank `WEBHOOK_SECRET` used to silently disable webhook authentication
entirely (`if settings.webhook_secret and ...` short-circuited to always pass), and the
same class of bug would apply to `API_KEY` if it were allowed to be blank. In
production (`ENVIRONMENT=production`, the default), both are hard requirements. A new
`ENVIRONMENT=development` mode exists specifically for local testing where neither is
configured - it is never the default, so forgetting to set it fails safe (refuses to
start) rather than failing open (starts unauthenticated).

## 2. RISK_ENFORCEMENT=true requires real account limits, or the app refuses to start
Extending the same discipline one step further: enabling kill-switch enforcement
against `ACCOUNT_*` placeholder defaults ($50k balance, $1k daily loss, etc. - see
`atlas/config.py`'s existing `account_configured` flag from Sprint 4) would be actively
misleading, not just incomplete - it would look like protection while enforcing
numbers that aren't your real funded-account rules. `validate_for_startup()` refuses to
start if `RISK_ENFORCEMENT=true` and any of the four `ACCOUNT_*` variables is unset.

## 3. The kill switch gates the `forward` callable, not `claim_and_forward` itself
`atlas/api/v1/webhook.py::_handle_entry`'s `do_forward()` closure now checks
`settings.risk_enforcement` and, if a real breach exists (via
`_risk_enforcement_block_reason`, which calls the exact same
`atlas.risk.compute_risk_snapshot` the display-only `GET /api/v1/risk` endpoint already
used), returns `(False, None, "blocked by risk engine: ...")` **without ever calling
`forward_to_pickmytrade`** - no HTTP call to PickMyTrade happens at all. Everything else
about `claim_and_forward`'s contract (the advisory-lock idempotency guarantee, the
`(forwarded, status_code, error)` tuple shape, storing the trade regardless of whether
it forwarded) is completely unchanged - this was a deliberate design constraint from
the "do not modify PickMyTrade relay semantics" rule: the kill switch decides *whether*
`forward_to_pickmytrade` gets called, never *how* it works. The trade is still stored,
still shows up in trade history/analytics, and AI entry scoring still runs exactly as
it would for any other entry (`background_tasks.add_task(run_entry_score, ...)` is
scheduled unconditionally, before this decision is even made) - a blocked entry looks
identical to a PickMyTrade-outage entry from every angle except the specific
`pmt_error` message, by design (analytics/AI must never know or care why a trade wasn't
forwarded).

## 4. The webhook secret is sanitized before persistence, not filtered on read
The Sprint 8 audit's sharpest finding was that a *correctly configured* secret still
leaked itself: `webhook.py` stored the entire raw request body (secret field included)
into `trades.raw_entry_payload`, which `GET /api/v1/trades/{id}` returns unfiltered.
The fix is at the write path, not the read path: `_sanitize_raw_body()` re-serializes
the payload with the `"secret"` key removed *before* it's ever written to the
database, so there is no raw_entry_payload row anywhere, past or future, that could
leak it - not "redact it when displaying," which would still leave the plaintext
sitting in Postgres. This does mean `raw_entry_payload` is no longer byte-for-byte
identical to what TradingView sent (it's the same JSON with one key removed) - a
deliberate, documented trade-off, since "debugging aid" and "never store the secret"
were in direct conflict and the security requirement won.

## 5. One low-level `WebhookPayload` model, deliberately permissive on unknown fields
`atlas/api/v1/webhook_models.py::WebhookPayload` replaces raw `payload.get(...)` access
with real Pydantic validation, but uses `extra="allow"` rather than a strict/closed
schema. This was a direct consequence of the "do not modify TradingView payloads" and
"do not modify PickMyTrade relay semantics" rules: `atlas/services/pickmytrade.py`'s
`PMT_FIELDS` extraction reads fields (`strategy_name`, `data`, `price`, `token`, etc.)
straight off the same dict this model produces, and a closed schema would either need
to duplicate that whole field list here (a second place that could drift from
`PMT_FIELDS`) or silently drop fields PickMyTrade needs. Only `correlation_id` (must be
non-blank) and `type` (must be one of the three known event types) are hard
requirements; every trade-data field stays optional, with type/range validation
applied *only when present* - `direction` must be `"long"`/`"short"` if given,
`quantity` must be positive if given, but a field being *absent* is not itself an
error. This is a deliberate asymmetry: rejecting a genuinely malformed value (wrong
type, an impossible number) is a very different, much stronger signal than "this
payload didn't happen to include an optional field" - and given the choice between
under- and over-rejecting a real TradingView signal, a missed trade is a worse outcome
than a slightly-degraded one, so validation stays permissive about *absence* and strict
about *wrongness*.

## 6. 400 vs 422: not-JSON stays 400, schema-invalid-JSON is now 422
Before this sprint, every rejection from the webhook handler (bad JSON, missing
correlation_id, unknown type) returned 400. As of Sprint 9, 400 is reserved
specifically for "this wasn't valid JSON at all" (unchanged), and every
`WebhookPayload` schema-validation failure returns 422 - the standard HTTP code for
"well-formed request, but it fails validation," and what FastAPI/Pydantic integrations
return by convention. `test_missing_correlation_id_is_rejected` (existing since Sprint
1) was updated to expect 422 instead of 400, since a missing `correlation_id` is now a
genuine schema-validation failure, not a hand-rolled dict-key check.

## 7. Authentication: one shared API key, applied at router-registration time
`atlas/api/security.py::require_api_key` is a single FastAPI dependency, applied via
`app.include_router(..., dependencies=[Depends(require_api_key)])` in `atlas/main.py`
for every router except `webhook` (its own shared-secret scheme - TradingView can't
send a custom `Authorization` header) and `health` (deliberately public - Railway's
health-check prober sends no custom headers, and the response reveals nothing beyond
"is the database reachable"). Router-level `dependencies=` was chosen over decorating
every individual route function specifically so a new route added to an already-
protected router can never accidentally ship unauthenticated - there's one line per
router to audit, not one per endpoint. Per the sprint's explicit instruction, this is a
single shared bearer token (`Authorization: Bearer <API_KEY>`), not per-user OAuth -
appropriate for what remains, today, a single-user tool.

## 8. `/api/v1/stream` gets a second auth path: the key as a query parameter
Browsers' native `EventSource` API cannot set custom request headers - there is no way
for the frontend's SSE client (`frontend/src/lib/live-updates.tsx`) to send
`Authorization: Bearer ...` on that one connection. `require_api_key_for_stream`
accepts the key via either the header (for parity/testing) or `?api_key=...` (what the
browser actually uses). This is a narrowly-scoped exception - every other endpoint
still requires the header - and a well-precedented pattern for SSE specifically, not a
general relaxation of the auth requirement.

## 9. `scripts/dev_seed_server.py` stays intentionally unauthenticated
The local dev harness never calls `Settings.validate_for_startup()` and its own
`build_app()` does not attach the `require_api_key` dependency to any router - it was
already a separate, stripped-down FastAPI app (in-memory repository, no Postgres, no
real Claude calls by default) explicitly documented as "not used in production." Adding
auth friction there would break the zero-config local dev workflow for no real safety
benefit, since nothing it touches is real. The frontend's `NEXT_PUBLIC_API_KEY` env var
is simply left unset for local dev against this server - the frontend only attaches an
`Authorization` header when that variable is present, so the same frontend code works
unmodified against both the dev harness (no header sent, none required) and a real
`atlas.main:app` deployment (header sent, required).

## 10. Rate limiting: slowapi, in-memory, keyed by IP
`atlas/rate_limit.py` wraps a single `slowapi.Limiter` (in-memory storage, keyed by
remote address) - consistent with this codebase's already-documented single-instance
assumption (`atlas/events/bus.py`'s `EventBus` makes the same trade-off). A generous
default (`200/minute`) covers the dashboard's own polling across ~10 endpoints;
`POST /webhook` gets a tighter, TradingView-appropriate `30/minute`; `POST
/ai/reports/{period}` gets the tightest limit of all (`5/minute`), since it's the one
endpoint in this system that costs real money per call (a real Anthropic API request) -
closing the Sprint 8 audit's specific finding that this endpoint was an unauthenticated,
unbounded billing-cost vector (it's no longer unauthenticated either, per decision #7,
but the rate limit is defense in depth even against a leaked/guessed key). Test
isolation: the limiter's counters are module-level state that persists across the whole
pytest session, so `tests/conftest.py` gained an autouse fixture that calls
`limiter.reset()` before and after every test.

## 11. Legacy HTML dashboard removed entirely, not just unlinked
`atlas/api/v1/dashboard.py` (server-rendered HTML via raw f-string interpolation of
trade fields, unescaped) was the concrete, exploitable mechanism behind the Sprint 8
audit's stored-XSS finding - chainable with the webhook-auth gap (decision #1) and the
historical lack of input validation (decision #5) into "attacker-controlled data
renders unescaped in a browser-facing page." Rather than adding auth or escaping to a
placeholder view that predates the real Next.js frontend by seven sprints, it was
deleted outright, along with `live/app.py` and `live/schema.sql` (the original Sprint-0
standalone implementation, dead code that duplicated the same vulnerable rendering
logic and was never wired into anything). `atlas/main.py` no longer mounts anything at
`/` - `/webhook` and `/health` remain the only unversioned, permanent routes.

## 12. Security headers: strict CSP is safe now that the backend serves no HTML
`atlas/main.py`'s `@app.middleware("http")` adds `X-Content-Type-Options`,
`X-Frame-Options`, `Strict-Transport-Security`, and `Content-Security-Policy:
default-src 'none'` to every response. The strict, maximally-restrictive CSP is only
safe *because* decision #11 removed the one HTML-rendering endpoint this sprint - the
backend now serves exclusively JSON and SSE (`text/event-stream`), neither of which a
browser executes as a document, so there is no first-party script/style for a policy to
break. FastAPI's auto-generated `/docs`, `/redoc`, and `/openapi.json` (which *are*
HTML/JS, and which reveal the full API surface publicly by default) are disabled
entirely in production (`docs_url=None` etc. when `ENVIRONMENT=production`), kept
enabled in development for convenience. The frontend (`frontend/next.config.ts`) gets
its own baseline headers plus a CSP scoped to `next build`/`next start` only (not `next
dev`, whose HMR/eval requirements could conflict with a strict policy) - `'unsafe-inline'`
is permitted for `style-src` only (Next.js may inject inline styles in some
configurations; inline styles cannot execute script) while `script-src` stays strict
(`'self'` only, no `unsafe-inline`/`unsafe-eval`).
