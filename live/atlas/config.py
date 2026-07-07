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
        self.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        self.claude_model = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
        self.pickmytrade_webhook_url = os.environ.get("PICKMYTRADE_WEBHOOK_URL", "")
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


settings = Settings()
