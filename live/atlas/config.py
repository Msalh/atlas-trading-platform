"""
Central configuration for the Atlas backend. Every environment-variable read in the
codebase goes through this module - nowhere else should call os.environ.get directly,
so there is exactly one place to see what the app depends on and one place to change
a default. Tests override attributes on the shared `settings` instance directly
(e.g. `monkeypatch.setattr(settings, "webhook_secret", "test-secret")`).
"""
import os


class Settings:
    def __init__(self):
        self.database_url = os.environ.get("DATABASE_URL", "")
        self.webhook_secret = os.environ.get("WEBHOOK_SECRET", "")
        # Sprint 3 (Market Engine): a SEPARATE shared secret from WEBHOOK_SECRET,
        # protecting POST /api/v1/market-state. Deliberately not reused from the
        # trade webhook - they protect different trust domains (market-state
        # ingestion vs. order-relay-adjacent trade events), and a leaked one
        # should never compromise the other. Same body-embedded-field,
        # constant-time-comparison scheme as WEBHOOK_SECRET - see
        # atlas/api/v1/market_state.py.
        self.market_state_webhook_secret = os.environ.get("MARKET_STATE_WEBHOOK_SECRET", "")
        self.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        self.claude_model = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
        self.pickmytrade_webhook_url = os.environ.get("PICKMYTRADE_WEBHOOK_URL", "")

        # Sprint 9: "production" (the default - fails safe) or "development". Only
        # "development" ever tolerates a missing WEBHOOK_SECRET/API_KEY - see
        # validate_for_startup() below. atlas.main:app (the real entrypoint) reads
        # this; scripts/dev_seed_server.py is a separate, intentionally-unauthenticated
        # local test harness that never calls validate_for_startup() at all.
        self.environment = os.environ.get("ENVIRONMENT", "production").strip().lower()
        # Sprint 9: shared API key required on every non-webhook, non-health endpoint
        # (see atlas/api/security.py). Single shared secret, not per-user - this
        # remains a single-user tool, not a multi-tenant system.
        self.api_key = os.environ.get("API_KEY", "")
        # Sprint 9: display-only by default (Sprint 4's original scope). Only when
        # this is explicitly "true" does a breached kill switch actually block new
        # PickMyTrade forwards - see atlas/api/v1/webhook.py's risk-enforcement gate.
        self.risk_enforcement = os.environ.get("RISK_ENFORCEMENT", "false").strip().lower() == "true"

        # Sprint 10: a Slack-compatible incoming webhook URL (also works with Discord
        # and most generic webhook receivers) - see atlas/alerting.py. If unset,
        # alerting is a no-op everywhere, the same "advisory only, gracefully absent"
        # pattern as PICKMYTRADE_WEBHOOK_URL/ANTHROPIC_API_KEY.
        self.alert_webhook_url = os.environ.get("ALERT_WEBHOOK_URL", "")
        # Sprint 10: how many CONSECUTIVE Claude failures (across entry scoring, post-
        # trade review, and reports combined) before atlas.alerting.ClaudeFailureTracker
        # sends one alert - see that class's docstring for why this is a streak count,
        # not "alert on every failure."
        self.claude_failure_alert_threshold = int(os.environ.get("CLAUDE_FAILURE_ALERT_THRESHOLD", "3"))
        # Market Engine Sprint 7 - see atlas/monitoring.py. Default 15 minutes:
        # roughly 3x a 5-minute bar interval, a buffer against normal
        # delivery/processing jitter without being so loose that a genuine
        # multi-bar gap goes unnoticed for a long time. Reuses
        # ALERT_WEBHOOK_URL (above) for delivery - unset means this is a
        # silent no-op, same "advisory only" pattern as everything else in
        # atlas/alerting.py.
        self.market_state_staleness_threshold_minutes = float(
            os.environ.get("MARKET_STATE_STALENESS_THRESHOLD_MINUTES", "15")
        )
        self.market_state_staleness_check_interval_seconds = float(
            os.environ.get("MARKET_STATE_STALENESS_CHECK_INTERVAL_SECONDS", "60")
        )
        # Comma-separated list of origins allowed to call the API cross-origin (the
        # Next.js frontend). Defaults to the local Next.js dev server so local
        # frontend development works with zero configuration; set this explicitly in
        # production to the deployed frontend's origin(s).
        self.frontend_origins = [
            o.strip() for o in os.environ.get("FRONTEND_ORIGINS", "http://localhost:3000").split(",") if o.strip()
        ]

        # Account risk parameters (Sprint 4). One account, one instrument (MNQ) in
        # practice today - see docs/sprint4/architecture-decisions.md for why this is
        # env-var config rather than an `accounts` table: there's nothing to key a
        # second row on yet, and adding one now would be schema speculation ahead of
        # an actual second account. The defaults below are round-number placeholders,
        # NOT your real funded-account rules - self.account_configured tells callers
        # whether they were actually set, so the UI can warn loudly instead of quietly
        # showing risk numbers computed against made-up limits.
        account_env_keys = [
            "ACCOUNT_STARTING_BALANCE", "ACCOUNT_DAILY_LOSS_LIMIT",
            "ACCOUNT_TRAILING_DRAWDOWN_LIMIT", "ACCOUNT_MAX_CONTRACTS",
        ]
        self.account_configured = all(os.environ.get(k) is not None for k in account_env_keys)
        self.account_starting_balance = float(os.environ.get("ACCOUNT_STARTING_BALANCE", "50000"))
        self.account_daily_loss_limit = float(os.environ.get("ACCOUNT_DAILY_LOSS_LIMIT", "1000"))
        self.account_trailing_drawdown_limit = float(os.environ.get("ACCOUNT_TRAILING_DRAWDOWN_LIMIT", "2000"))
        self.account_max_contracts = int(os.environ.get("ACCOUNT_MAX_CONTRACTS", "5"))
        # Dollars per point per contract for the traded instrument. MNQ (Micro Nasdaq)
        # = $2/point - also a placeholder until a real symbols table exists (see the
        # same architecture-decisions.md note).
        self.account_point_value = float(os.environ.get("ACCOUNT_POINT_VALUE", "2.0"))

        # Sprint 8.2 (Railway Staging Deployment): where the Research Ledger's
        # nine JSONL stores (atlas/research/stores.py) live on disk. Defaulted,
        # never added to validate_for_startup()'s hard-blocking checks below -
        # deliberately consistent with this deployment's own established
        # posture for research-only concerns (see
        # atlas/research_export/startup_check.py's "never block LIVE, never
        # crash startup" contract): an unset or non-persistent value degrades
        # research readiness (GET /status's research_ledger field,
        # atlas/research_deploy/startup_check.py), it never takes down
        # webhook/trades/risk endpoints. In a real Railway deployment this
        # must be set to the mounted Volume's path - see
        # docs/staging/deployment-checklist.md.
        self.research_ledger_dir = os.environ.get("RESEARCH_LEDGER_DIR", "data/research")

    def validate_for_startup(self) -> None:
        """Called once from atlas/main.py's lifespan, before the app accepts any
        traffic - the same "refuse to start rather than run unsafely" discipline
        atlas/db.py's create_pool() already uses for a missing DATABASE_URL, applied
        to the Sprint 9 security gaps found in the Sprint 8 audit:

        - A missing WEBHOOK_SECRET used to silently disable webhook authentication
          entirely (atlas/api/v1/webhook.py's check was `if settings.webhook_secret
          and ...` - a blank secret short-circuited the check to always pass).
        - The same class of bug would apply to API_KEY (atlas/api/security.py) if it
          were allowed to be blank in production.
        - RISK_ENFORCEMENT=true against un-configured (placeholder) account limits
          would enforce against numbers that aren't your real funded-account rules -
          arguably worse than no enforcement, since it looks safe but isn't.

        Deliberately NOT called by scripts/dev_seed_server.py, which is a separate,
        already-documented-as-unauthenticated local dev harness - set
        ENVIRONMENT=development for any other kind of informal local testing against
        atlas.main:app itself.
        """
        if self.environment not in ("production", "development"):
            raise RuntimeError(
                f"ENVIRONMENT={self.environment!r} is not recognized - must be "
                f"'production' (the default) or 'development'."
            )
        if self.environment != "production":
            return

        missing = []
        if not self.webhook_secret:
            missing.append("WEBHOOK_SECRET")
        if not self.api_key:
            missing.append("API_KEY")
        if not self.market_state_webhook_secret:
            missing.append("MARKET_STATE_WEBHOOK_SECRET")
        if missing:
            raise RuntimeError(
                f"{', '.join(missing)} not set. Refusing to start in production mode "
                f"(ENVIRONMENT=production, the default) without it - an unset webhook "
                f"secret or API key means that check is silently disabled, not "
                f"enforced. Set the missing variable(s), or set ENVIRONMENT=development "
                f"for local testing only (never for a real deployment)."
            )
        if self.risk_enforcement and not self.account_configured:
            raise RuntimeError(
                "RISK_ENFORCEMENT=true but ACCOUNT_STARTING_BALANCE/ACCOUNT_DAILY_LOSS_LIMIT/"
                "ACCOUNT_TRAILING_DRAWDOWN_LIMIT/ACCOUNT_MAX_CONTRACTS are not all set. "
                "Refusing to start: enforcing the kill switch against placeholder default "
                "limits (not your real funded-account rules) would be actively misleading - "
                "it would look like protection while enforcing numbers that mean nothing. "
                "Set all four account variables, or leave RISK_ENFORCEMENT unset/false."
            )


settings = Settings()
