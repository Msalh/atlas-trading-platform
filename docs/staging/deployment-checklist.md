# Staging Deployment Checklist

Step-by-step, from the current local-only state to a verified staging deployment. This
is a **staging** environment - real orders must not be possible until you explicitly
decide otherwise (see the Safety Gates section before you start, and again before you
finish).

**What I (the assistant) cannot do:** I have no Railway or Vercel account access, no
deployment API, and no ability to click through their dashboards. Every step below
that says "in Railway's dashboard" or "in Vercel's dashboard" is something you need to
do yourself. What I've prepared is everything that makes those steps fast and
unambiguous: the exact settings, the exact environment variables, and a full set of
scripts to verify each one afterward (`live/scripts/smoke_test.sh`).

**What I will not do without you explicitly telling me to, separately from this
checklist:** commit the current local changes, push to any git remote, or touch
`PICKMYTRADE_WEBHOOK_URL`/`ACCOUNT_*`/`RISK_ENFORCEMENT` in a way that could enable a
real order. Step 0 below explains why committing/pushing is a real prerequisite here
and asks you to confirm it separately.

---

## Step 0 - Prerequisite: a pushed git remote

Railway and Vercel both deploy by watching a GitHub repository. Right now, this
project has **no remote configured** (`git remote -v` is empty) and 69 files of
Sprint 6-10 work sitting uncommitted locally - per every sprint's standing
instruction, none of it has been committed or pushed.

Before anything below can happen for real:
1. Create a GitHub repository (empty, private is recommended given this will contain
   deployment configuration even though secrets themselves stay in env vars, not code).
2. Tell me the repo URL and confirm you want me to commit the current work and push it
   there - I will not do this as an implicit side effect of this checklist. This is a
   separate, explicit decision from "prepare the deployment docs," which is what this
   message covers.
3. Once pushed, Railway/Vercel can each be pointed at that same repo (as a monorepo -
   both platforms support setting a **Root Directory** so the backend service builds
   from `live/` and the frontend project builds from `frontend/`, independently, from
   the one repo).

Everything from Step 1 onward assumes this has happened.

---

## Safety Gates - read before and after every step below

- [ ] `PICKMYTRADE_WEBHOOK_URL` stays **unset** in Railway's environment variables for
      this staging deploy, unless you have explicitly told me you want to connect to
      real PickMyTrade. Unset means every entry is stored and scored but never
      forwarded (`pmt_forwarded: false`, `pmt_error: "PICKMYTRADE_WEBHOOK_URL not
      configured"`) - this is the single control that guarantees no real order can be
      placed through this deployment.
- [ ] `RISK_ENFORCEMENT` stays `false` (the default - just leave it unset) unless
      you're specifically testing the kill switch, and even then, that only affects
      *whether a forward is blocked*, not whether one can happen in the first place -
      the PMT URL gate above is the real safety boundary.
- [ ] `ACCOUNT_STARTING_BALANCE`/`ACCOUNT_DAILY_LOSS_LIMIT`/
      `ACCOUNT_TRAILING_DRAWDOWN_LIMIT`/`ACCOUNT_MAX_CONTRACTS` should be staging/test
      values (or left unset entirely), never your real funded-account numbers - this
      is a staging environment, not the funded account.
- [ ] After deployment, run `live/scripts/smoke_test.sh`'s `check_no_real_orders`
      check (see below) and confirm it reports PMT forwarding is disabled before
      considering this deploy "done."

---

## Step 1 - Railway: create the project and Postgres

1. In Railway, **New Project** → **Deploy from GitHub repo** → select the repo from
   Step 0.
2. Railway will try to auto-detect a service from the repo root - **delete that
   initial auto-detected service** if it doesn't correctly target `live/` (monorepo
   root detection is unreliable); you'll add the correct one in the next step.
3. **New** → **GitHub Repo** (same repo again) → in the new service's **Settings** →
   **Root Directory**, set it to `live`. Railway will now build/deploy only that
   subdirectory, picking up `live/Procfile`
   (`web: uvicorn atlas.main:app --host 0.0.0.0 --port $PORT`) automatically.
4. In the same project, **New** → **Database** → **Add PostgreSQL**. Railway
   provisions a Postgres instance and automatically injects `DATABASE_URL` into every
   other service in the same project - you do not need to copy/paste a connection
   string manually.
5. Do **not** deploy yet - set environment variables first (Step 2), since
   `Settings.validate_for_startup()` will crash-loop the service without them.

## Step 2 - Railway: environment variables

In the backend service's **Variables** tab, set:

| Variable | Staging value | Notes |
|---|---|---|
| `DATABASE_URL` | *(auto-injected by the Postgres plugin)* | Confirm it's present - don't set it manually. |
| `WEBHOOK_SECRET` | a random value you generate, e.g. `openssl rand -hex 32` | Required - the app refuses to start without it (Sprint 9). |
| `API_KEY` | a **different** random value, e.g. `openssl rand -hex 32` | Required, and must not equal `WEBHOOK_SECRET` - they protect different things. |
| `ENVIRONMENT` | `production` | Yes, even for staging - this is what enables the startup safety checks. There is no separate "staging" mode; staging-ness comes from `PICKMYTRADE_WEBHOOK_URL` being unset, not from a relaxed `ENVIRONMENT`. |
| `ANTHROPIC_API_KEY` | your real key, or leave unset | Optional - if unset, AI features run in the same graceful "not configured" degraded mode they've always had; no order-execution impact either way. |
| `PICKMYTRADE_WEBHOOK_URL` | **leave unset** | See Safety Gates above. |
| `FRONTEND_ORIGINS` | `https://<your-vercel-project>.vercel.app` | Set once you know the Vercel URL from Step 4 - can be updated after the fact. |
| `RISK_ENFORCEMENT` | *(leave unset, defaults to `false`)* | See Safety Gates above. |
| `ALERT_WEBHOOK_URL` | optional - a Slack/Discord incoming webhook, or a throwaway endpoint like a [webhook.site](https://webhook.site) URL for testing alerting itself | Leave unset if you don't want alerting active yet. |
| `CLAUDE_FAILURE_ALERT_THRESHOLD` | *(leave unset, defaults to `3`)* | |

Do **not** set any `ACCOUNT_*` variable unless you're deliberately testing the risk
snapshot/kill-switch display with fake numbers.

## Step 3 - Railway: deploy and verify startup

1. Trigger the deploy (Railway does this automatically once variables are saved, or
   use **Deploy** manually).
2. Watch the deploy logs. Expect to see migrations apply
   (`applying migration 0001_init.sql`, `0002_add_quantity.sql`, `0003_ai_notes.sql`,
   `0004_ai_intelligence_fields.sql`, in order) followed by
   `Uvicorn running on http://0.0.0.0:$PORT`.
3. **If it crash-loops:** check the logs for a `RuntimeError` from
   `Settings.validate_for_startup()` first - it names exactly which variable is
   missing. This is by far the most likely failure mode for a first deploy.
4. Once it's up, copy the service's public URL (Railway generates one under
   **Settings** → **Networking** → **Generate Domain** if you haven't already).

## Step 4 - Vercel: create the frontend project

1. **Add New** → **Project** → import the same GitHub repo.
2. In the import screen (or **Settings** → **General** afterward), set **Root
   Directory** to `frontend`. Vercel auto-detects Next.js from there - no other build
   configuration needed.
3. **Settings** → **Environment Variables**:

| Variable | Staging value |
|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | the Railway backend URL from Step 3.4 |
| `NEXT_PUBLIC_API_KEY` | the same `API_KEY` value you set in Railway (Step 2) |

4. Deploy. Once it's live, copy the Vercel URL and go back to Railway's
   `FRONTEND_ORIGINS` variable (Step 2) to set it correctly, then redeploy the backend
   so CORS allows the real frontend origin.

## Step 5 - Verify everything

Run `live/scripts/smoke_test.sh` against the deployed backend (see that script's own
header for usage) - it covers migrations, auth, webhook secret rejection, SSE, health/
status, and the "no real orders possible" check in one pass. Then:

- [ ] Open the Vercel URL in a browser. Confirm the dashboard loads, the connection
      status dot goes live, and there are no console errors.
- [ ] Confirm `GET /api/v1/status`'s `pickmytrade.configured` is `false` (see Safety
      Gates - this is the definitive check that no real order can be placed).
- [ ] If you set `ALERT_WEBHOOK_URL` to a test endpoint (e.g. webhook.site), manually
      verify it by POSTing a webhook with the wrong secret a few times and confirming
      *nothing* fires (auth rejection isn't an alerting event) - then see
      `docs/sprint10/deployment-runbook.md`'s incident-response section for how a real
      alert would actually look once real traffic flows.

Once every item above is checked, staging is verified. This does **not** mean it's
ready for real money - see the Safety Gates section again, and do not change
`PICKMYTRADE_WEBHOOK_URL` until you've separately, explicitly decided to.

---

## Rollback

See `docs/staging/rollback-plan.md`.
