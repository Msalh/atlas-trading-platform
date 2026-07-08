# Sprint 9 - Security Notes

Written as the companion to the Sprint 8 engineering audit - each finding below is
listed against what actually changed, in the same order the audit raised them, plus
what remains open. This is not a "we're done" document; it's the honest state after
this sprint's fixes.

## Sprint 8 Critical findings - status

### 1. Webhook auth silently disabled when `WEBHOOK_SECRET` unset - FIXED
`atlas/config.py::Settings.validate_for_startup()` now refuses to start in production
(the default) without `WEBHOOK_SECRET` set. The runtime check itself
(`atlas/api/v1/webhook.py::_secret_matches`) also moved to a constant-time comparison
(`hmac.compare_digest`), closing a secondary timing-attack surface that existed
alongside the main bug.

### 2. Webhook secret leaks itself via `raw_entry_payload` - FIXED
The secret is stripped from the payload *before* it is ever persisted
(`_sanitize_raw_body`) - see architecture-decisions.md #4. `test_webhook_secret_is_never_persisted_in_raw_entry_payload`
regression-tests this directly against the stored row, not just the response body.

### 3. Zero authentication on every REST read/write-trigger endpoint - FIXED
Every non-webhook, non-health endpoint now requires `Authorization: Bearer <API_KEY>`
(`/api/v1/stream` also accepts `?api_key=...`, since browsers' `EventSource` can't set
headers). See architecture-decisions.md #7-8.

### 4. Kill switch cannot stop trading - FIXED (opt-in)
`RISK_ENFORCEMENT=true` (default `false`) makes a breached daily-loss-limit or
trailing-drawdown actually block the PickMyTrade forward. Default-off was an explicit
sprint requirement, not an oversight - see the Remaining Risks section below for what
that means in practice.

### 5. Stored XSS in the legacy `/` dashboard - FIXED (endpoint removed)
`atlas/api/v1/dashboard.py` no longer exists. There is no HTML-rendering endpoint left
in the backend at all - see architecture-decisions.md #11.

## Sprint 8 High findings - status

### 6. No rate limiting - FIXED
`POST /webhook` (30/minute), `POST /ai/reports/{period}` (5/minute - the one endpoint
that costs real money per call), and a `200/minute` default covering everything else
authenticated. See architecture-decisions.md #10.

### 7. No input validation on the webhook payload - FIXED
`atlas/api/v1/webhook_models.py::WebhookPayload` - see architecture-decisions.md #5-6.

### 8. No test for the `WEBHOOK_SECRET`-unset scenario or pool-exhaustion-under-load -
**PARTIALLY ADDRESSED**. `tests/test_config_validation.py` now directly tests that a
missing `WEBHOOK_SECRET`/`API_KEY` refuses startup in production and is tolerated in
development - the exact scenario that caused Critical finding #1 now has regression
coverage. The PickMyTrade-hang-while-advisory-lock-held scenario (pool exhaustion under
a slow broker response) is **still untested** - out of scope for this sprint, which was
scoped to auth/validation/enforcement, not concurrency/load testing.

### 9. No CI/CD - **NOT ADDRESSED THIS SPRINT**. Out of scope (see Sprint 8 audit's
proposed Sprint 10: CI/CD & Observability).

### 10. Zero frontend automated tests - **NOT ADDRESSED THIS SPRINT**. Same as above.

### 11. No monitoring/alerting on operational failures - **NOT ADDRESSED THIS SPRINT**.
A blocked-by-risk-engine or auth-rejected request is now visible in structured
`pmt_error`/401 responses and server logs, which is marginally better than before, but
there is still no active alerting (Slack/email/PagerDuty) on any failure mode.

## What this sprint did NOT touch (by explicit instruction)

- Strategy logic, TradingView payload contract, PickMyTrade relay semantics (the actual
  HTTP call, its 15s timeout, `PMT_FIELDS` extraction) - all byte-for-byte unchanged.
- The single-process assumption behind `EventBus`/`SystemStatus`/SSE (Sprint 8 audit
  Medium finding #12) - still a hard horizontal-scaling constraint, unaddressed.
- Missing database indexes on `trades.status`/`trades.closed_at`, `TEXT` timestamps
  instead of `TIMESTAMPTZ`, the un-advisory-locked migration runner (Sprint 8 audit
  Medium findings #14-17) - all still open.
- Backup/PITR strategy for the production Postgres instance - still unconfirmed.

## Remaining security risks after this sprint

These are real, and worth stating plainly rather than implying this sprint closed
everything:

1. **`RISK_ENFORCEMENT` defaults to `false`.** Per this sprint's explicit
   specification, enforcement is opt-in. Until you set `RISK_ENFORCEMENT=true` (and all
   four `ACCOUNT_*` variables, which the app now requires alongside it), a breached
   daily-loss-limit or trailing-drawdown remains purely informational, exactly as
   before this sprint - it will not stop a bad session from continuing to place real
   orders. **This is the single most important variable to set correctly before
   connecting to a real funded account**, and it is not set by default.

2. **The API key is one shared secret, not per-user/per-device.** Anyone who obtains
   it (a leaked `.env`, a compromised frontend deployment, a browser dev-tools glance at
   `NEXT_PUBLIC_API_KEY` - which, being `NEXT_PUBLIC_*`, is bundled into the frontend's
   client-side JavaScript and is not actually secret from anyone who can view page
   source) has full access to every protected endpoint. This is an explicit,
   accepted trade-off for a single-user tool ("do NOT implement OAuth" was a direct
   instruction) - but it means the API key is a shared-tool safeguard against casual/
   automated discovery of a public URL, not a hardened per-identity credential. Rotate
   it if you ever suspect it's been exposed, the same way you'd rotate `WEBHOOK_SECRET`.

3. **Rate limiting is in-memory and per-process.** A determined attacker distributing
   requests across many source IPs isn't meaningfully slowed by an IP-keyed limiter.
   This raises the bar against casual abuse and cost-runaway from a single leaked key,
   it does not make the system DoS-proof.

4. **The frontend's CSP has not been verified against a real production
   deployment.** `frontend/next.config.ts`'s CSP was written conservatively and
   verified to not break `next build`, but Next.js's exact script-loading behavior in
   a real Vercel deployment can occasionally require nonce/hash adjustments that only
   surface at runtime. Verify the browser console shows no CSP violations after the
   first real deploy, before relying on it as a hard XSS backstop.

5. **No automated test exists for concurrent load against a real Postgres instance
   under this sprint's changes** (the advisory-lock guarantee itself remains
   well-tested per Sprint 8's audit, but the interaction between that lock and
   `RISK_ENFORCEMENT`'s extra `list_recent`/`compute_risk_snapshot` call on the entry
   path has only been tested against the in-memory repository, not real Postgres under
   load).

6. **Everything in this sprint has been tested locally against an in-memory
   repository and mocked Claude/PickMyTrade calls.** None of it has been verified
   against a real Postgres deployment, a real `ANTHROPIC_API_KEY`, or a real
   `PICKMYTRADE_WEBHOOK_URL` (no `ANTHROPIC_API_KEY`/real Postgres available in this
   sandbox) - see the deployment checklist for what to verify before a real deploy.
