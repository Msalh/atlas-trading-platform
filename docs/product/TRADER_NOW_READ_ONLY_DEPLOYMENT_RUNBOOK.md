# TraderNow Read-Only Service Deployment Runbook

## Boundary

The dedicated process starts `atlas.read_only_service:app`. It exposes only:

- `GET /health` — public process liveness
- `GET /readiness` — bearer-authenticated database and assembly readiness
- `GET /api/v1/trader-now` — bearer-authenticated read-only analysis

It does not import the monolithic entrypoint, run migrations, register ingestion or
trade routes, or initialize broker, AI, research-write, promotion, event-subscriber,
or execution workflows.

## Required configuration

Set all of the following explicitly:

- `ENVIRONMENT=production`
- `TRADER_NOW_SERVICE_MODE=read_only`
- `DATABASE_URL` using the dedicated read-only role
- `API_KEY`
- `TRADER_NOW_PRODUCT=MNQ`
- `TRADER_NOW_CONTRACT_SYMBOL`
- `TRADER_NOW_CONTRACT_RESOLUTION_VERSION`
- `TRADER_NOW_CONTRACT_EFFECTIVE_DATE`
- `TRADER_NOW_CALENDAR_VERSION`
- `TRADER_NOW_HOLIDAYS_JSON`
- `TRADER_NOW_EARLY_CLOSES_JSON`

No webhook, broker, Anthropic, research-ledger, account, or execution credential is
required by this service.

The monolithic Atlas service separately exposes
`GET /api/v1/trader-now/results`. That route does not use this read-only service's
`API_KEY` and does not fall back to the monolithic service's broader `API_KEY`.
Configure an independent, server-only `TRADER_NOW_RESULTS_API_KEY` on the monolithic
Atlas service and on its authorized server-side consumer. Never place it in browser
code, a `NEXT_PUBLIC_*` variable, a URL, logs, evidence, or committed files.

Roll out that credential in this order:

1. Configure `TRADER_NOW_RESULTS_API_KEY` on the Atlas backend before deploying the
   code that requires it.
2. Deploy the backend and verify missing, invalid, and broader `API_KEY` credentials
   receive `401`.
3. Configure the same credential through the consumer's server-only secret interface.
4. Deploy the consumer and verify the endpoint succeeds without exposing credentials
   to the browser.

Rollback the application revision and its configuration as one unit. Keep the
broader `API_KEY` unchanged; never make it a fallback for the results route.

## PostgreSQL role

Create the role through the approved database-administration workflow. Replace every
placeholder without recording the password in shell history or logs:

```sql
CREATE ROLE <role>
    LOGIN
    PASSWORD '<managed-secret>'
    NOINHERIT
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOREPLICATION
    NOBYPASSRLS;
REVOKE ALL ON DATABASE <database> FROM <role>;
GRANT CONNECT ON DATABASE <database> TO <role>;
REVOKE ALL ON SCHEMA public FROM <role>;
GRANT USAGE ON SCHEMA public TO <role>;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM <role>;
GRANT SELECT ON TABLE public.market_state_events TO <role>;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM <role>;
ALTER ROLE <role> SET default_transaction_read_only = on;
```

Do not grant table writes, sequence access, schema creation, ownership, migration,
or elevated role privileges. The process also requests
`default_transaction_read_only=on` on every pooled connection and verifies it at
startup. Before deployment, verify `rolsuper`, `rolinherit`, `rolcreatedb`,
`rolcreaterole`, `rolreplication`, and `rolbypassrls` are all false; schema `CREATE`
is false; table `SELECT` is true; and table `INSERT`, `UPDATE`, `DELETE`, and
`TRUNCATE` plus every sequence privilege are false. If `PUBLIC` grants schema
`CREATE` in the target database, the database administrator must revoke that broader
grant or use a dedicated schema whose `PUBLIC` privileges are already restricted.

## Start and verify

Start without running a migration command:

```text
uvicorn atlas.read_only_service:app --host 0.0.0.0 --port $PORT
```

Verify:

1. Startup logs contain `trader_now_read_service_started`.
2. `GET /health` returns `200` without credentials.
3. `GET /readiness` returns `401` without credentials and `200` with the bearer key.
4. An authenticated TraderNow request for exactly `MNQ`, `5m`, and
   `displacement_volume_context` returns `trader_now_response.v1`.
5. A valid no-data result remains `200` with explicit unavailable sections.
6. Route inspection shows only health, readiness, and TraderNow.
7. Logs contain correlation IDs and latency but no credentials or market payloads.

Example request:

```text
GET /api/v1/trader-now?symbol=MNQ&timeframe=5m&strategy_id=displacement_volume_context
Authorization: Bearer <API_KEY>
```

## Contract rollover verification

Before changing the active contract, confirm that `market_state_events` contains the
new exact MNQ identity. Change the contract symbol, resolution version, and effective
date together. Review holiday overrides, restart the service, require successful
readiness, and verify that the response resolves the intended contract. There is no
automatic rollover.

## Rollback

1. Restore the previous known-good service version and configuration as one unit.
2. Do not change or rotate backend trading credentials.
3. Confirm `/health`, authenticated `/readiness`, and the authenticated no-data or
   populated TraderNow response.
4. Inspect logs for startup failures and database permission errors.
5. Confirm again that no write-capable routes are mounted.

This runbook does not activate live trading and does not authorize deployment.
