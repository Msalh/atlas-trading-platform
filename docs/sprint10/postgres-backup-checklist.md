# Sprint 10 - PostgreSQL Backup & Point-in-Time Recovery Checklist

The Sprint 8 audit flagged that no backup/PITR strategy was ever confirmed for the
production Postgres instance. This is a checklist to work through once a real Railway
Postgres is provisioned - nothing here has been executed against a real instance (none
is available in this sandbox), and this doc does not substitute for actually doing it.

## 1. Confirm what Railway gives you by default

Railway's managed Postgres plugin includes automatic daily backups on paid plans, with
a retention window that depends on your plan tier. This is **not enabled by default on
every plan** and the retention window may be shorter than you want for a real funded
account's transaction history.

- [ ] Open the Postgres service in the Railway dashboard → **Settings** → **Backups**.
- [ ] Confirm automatic backups are actually turned on (don't assume).
- [ ] Note the retention window (how many days of backups are kept).
- [ ] Note the backup frequency (daily is Railway's default - confirm it hasn't been
      changed).
- [ ] If your plan doesn't include backups, or the retention window is too short for
      your risk tolerance, either upgrade the plan or implement the manual `pg_dump`
      supplement below.

## 2. Point-in-time recovery (PITR)

Daily snapshots alone only let you restore to *yesterday's* state, losing up to a full
day of trades if something goes wrong mid-session. True PITR (replaying the WAL to any
specific timestamp) is what actually protects against "I need the database as it was
10 minutes before the bad migration/bad deploy."

- [ ] Confirm whether your Railway Postgres plan supports PITR specifically (distinct
      from plain daily backups - check Railway's current plan comparison, this changes
      over time).
- [ ] If it does, note the actual granularity/window Railway advertises (some managed
      Postgres PITR windows are as short as a few days).
- [ ] If it doesn't, decide whether that's acceptable for this system's risk profile.
      Given this trades a live funded account, a same-day incident (a bad deploy that
      corrupts data mid-session) recovering only to last night's snapshot is a real
      gap - weigh this against the cost of a plan that includes PITR.

## 3. Manual `pg_dump` supplement (belt and suspenders)

Regardless of what Railway provides, an independent, off-platform backup is cheap
insurance against a Railway-side incident affecting both your database *and* its
backups simultaneously (unlikely, but the entire point of a backup is covering the
unlikely case).

- [ ] Set up a scheduled job (a simple cron on any always-on machine, or a scheduled
      GitHub Action using `workflow_dispatch` + a cron trigger) that runs:
      ```bash
      pg_dump "$DATABASE_URL" --format=custom --file="atlas-backup-$(date +%Y%m%d).dump"
      ```
- [ ] Upload the resulting file to storage independent of Railway (S3, Backblaze,
      even a private git LFS repo for a database this small) - a backup stored next to
      the thing it's backing up doesn't protect against a platform-wide incident.
- [ ] Decide a retention policy (e.g., keep daily dumps for 30 days, weekly for a
      year) and actually prune old ones - unbounded accumulation isn't "safe," it's
      just deferred cleanup work.
- [ ] This system's data volume is small (a handful of trades a day - see every
      sprint's "generous scan limit" comments throughout `atlas/`) - a full `pg_dump`
      takes seconds, there's no reason to reach for incremental/differential backup
      tooling here.

## 4. Restore testing - the step everyone skips

A backup that has never been restored is a hypothesis, not a backup.

- [ ] At least once, actually restore a `pg_dump` output into a fresh, disposable
      Postgres instance:
      ```bash
      createdb atlas_restore_test
      pg_restore --dbname=atlas_restore_test atlas-backup-YYYYMMDD.dump
      ```
- [ ] Point a local `atlas.main:app` (with `DATABASE_URL` set to the restored test
      database) at it and confirm `GET /api/v1/health` reports `ok: true` and
      `GET /api/v1/trades` returns real, sane-looking data - not just that the
      `pg_restore` command exited 0.
- [ ] If using Railway's built-in backups, actually click through Railway's restore
      flow against a throwaway/staging service at least once *before* you need it
      under pressure during a real incident - the first time you use a recovery
      procedure should not be during the incident itself.
- [ ] Repeat this restore test periodically (e.g., quarterly) - a working restore
      procedure today doesn't guarantee Railway hasn't changed its restore UX by the
      time you actually need it.

## 5. What to actually do if you need to restore

This is a placeholder checklist for a real incident - fill in the specifics once
you've done the restore test above at least once and know your actual Railway
dashboard flow:

- [ ] Stop `atlas.main:app` first (or at minimum, stop the webhook from receiving new
      traffic) - restoring into a database that's actively being written to by a live
      process is asking for a race, and a stray webhook delivery during a restore
      could interleave with the restored data in a confusing way.
- [ ] Restore via Railway's dashboard (or the manual `pg_restore` path from #4) into
      either the same instance (if Railway supports in-place restore) or a fresh one
      you then repoint `DATABASE_URL` at.
- [ ] Run `GET /api/v1/health` before resuming traffic - don't assume the restore
      succeeded just because the restore command didn't error.
- [ ] Spot-check the most recent few trades against your broker's own records
      (PickMyTrade's dashboard, or your prop firm's platform) before trusting the
      restored `pmt_forwarded`/`realized_pnl` values - a PITR restore to a timestamp
      slightly before an in-flight webhook delivery could leave one trade in an
      inconsistent state (e.g. `pmt_forwarded=false` when the order actually went
      through) that only your broker's own record can resolve.
