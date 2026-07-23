"""
Tests for Settings.validate_for_startup() (Sprint 9) - the "refuse to start unsafely"
gate covering the exact class of bug the Sprint 8 audit found: a missing
WEBHOOK_SECRET used to silently disable authentication entirely rather than being
caught before the app ever accepted traffic. Same discipline atlas/db.py's
create_pool() already applies to a missing DATABASE_URL, extended here to
WEBHOOK_SECRET/API_KEY and to RISK_ENFORCEMENT against un-configured account limits.

Constructs real Settings() instances from monkeypatched environment variables (rather
than hand-building a bare object) so the actual os.environ parsing in Settings.__init__
- e.g. RISK_ENFORCEMENT's "true"/"false" string handling, account_configured's
all-four-or-none check - is exercised too, not just validate_for_startup() in isolation.
"""
import pytest

from atlas.config import Settings

BASE_ENV = {
    "WEBHOOK_SECRET": "wh-secret",
    "API_KEY": "api-key",
    "MARKET_STATE_WEBHOOK_SECRET": "ms-secret",
    "ENVIRONMENT": "production",
    "RISK_ENFORCEMENT": "false",
    "ACCOUNT_STARTING_BALANCE": "50000",
    "ACCOUNT_DAILY_LOSS_LIMIT": "1000",
    "ACCOUNT_TRAILING_DRAWDOWN_LIMIT": "2000",
    "ACCOUNT_MAX_CONTRACTS": "5",
}


def _settings(monkeypatch, **overrides):
    env = {**BASE_ENV, **overrides}
    for key, value in env.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    return Settings()


def test_refuses_to_start_without_webhook_secret_in_production(monkeypatch):
    s = _settings(monkeypatch, WEBHOOK_SECRET="")
    with pytest.raises(RuntimeError, match="WEBHOOK_SECRET"):
        s.validate_for_startup()


def test_refuses_to_start_without_api_key_in_production(monkeypatch):
    s = _settings(monkeypatch, API_KEY="")
    with pytest.raises(RuntimeError, match="API_KEY"):
        s.validate_for_startup()


def test_refuses_to_start_without_either_secret_lists_both(monkeypatch):
    s = _settings(monkeypatch, WEBHOOK_SECRET="", API_KEY="")
    with pytest.raises(RuntimeError, match="WEBHOOK_SECRET.*API_KEY|API_KEY.*WEBHOOK_SECRET"):
        s.validate_for_startup()


def test_refuses_to_start_without_market_state_webhook_secret_in_production(monkeypatch):
    # Sprint 3 (Market Engine): a separate secret from WEBHOOK_SECRET/API_KEY,
    # held to the exact same "refuse to start, don't silently disable the
    # check" standard - see atlas/config.py's own comment on why it's separate.
    s = _settings(monkeypatch, MARKET_STATE_WEBHOOK_SECRET="")
    with pytest.raises(RuntimeError, match="MARKET_STATE_WEBHOOK_SECRET"):
        s.validate_for_startup()


def test_development_mode_tolerates_missing_secrets(monkeypatch):
    s = _settings(
        monkeypatch, ENVIRONMENT="development", WEBHOOK_SECRET="", API_KEY="", MARKET_STATE_WEBHOOK_SECRET="",
    )
    s.validate_for_startup()  # must not raise


def test_production_mode_with_secrets_set_starts_cleanly(monkeypatch):
    s = _settings(monkeypatch)
    s.validate_for_startup()  # must not raise


def test_risk_enforcement_without_account_configured_refuses_to_start(monkeypatch):
    s = _settings(monkeypatch, RISK_ENFORCEMENT="true", ACCOUNT_MAX_CONTRACTS=None)
    with pytest.raises(RuntimeError, match="RISK_ENFORCEMENT"):
        s.validate_for_startup()


def test_risk_enforcement_with_account_configured_starts_cleanly(monkeypatch):
    s = _settings(monkeypatch, RISK_ENFORCEMENT="true")
    s.validate_for_startup()  # must not raise


def test_risk_enforcement_case_insensitive_true(monkeypatch):
    s = _settings(monkeypatch, RISK_ENFORCEMENT="TRUE")
    assert s.risk_enforcement is True


def test_unrecognized_environment_value_refuses_to_start(monkeypatch):
    s = _settings(monkeypatch, ENVIRONMENT="staging")
    with pytest.raises(RuntimeError, match="ENVIRONMENT"):
        s.validate_for_startup()


# ---- Sprint 8.2: RESEARCH_LEDGER_DIR (defaulted attribute, never hard-required) ----

def test_research_ledger_dir_raw_attribute_is_blank_when_unset(monkeypatch):
    """The raw attribute is never defaulted - only
    resolved_research_ledger_dir() applies any environment-dependent
    fallback. Keeping the raw value undefaulted is what lets that method
    tell "explicitly set" apart from "absent" in every environment."""
    s = _settings(monkeypatch, RESEARCH_LEDGER_DIR=None)
    assert s.research_ledger_dir == ""


def test_research_ledger_dir_reads_the_environment_override(monkeypatch):
    s = _settings(monkeypatch, RESEARCH_LEDGER_DIR="/data/research")
    assert s.research_ledger_dir == "/data/research"


def test_missing_research_ledger_dir_does_not_block_production_startup(monkeypatch):
    """Deliberately NOT added to the hard-blocking missing-vars check above -
    a research-storage misconfiguration degrades research readiness
    (GET /status), it must never crash-loop the whole app the way a missing
    WEBHOOK_SECRET/API_KEY correctly does."""
    s = _settings(monkeypatch, RESEARCH_LEDGER_DIR=None)
    s.validate_for_startup()  # must not raise


# ---- Sprint 8.2, production-safety correction: resolved_research_ledger_dir() ----

def test_required_1_development_falls_back_to_the_local_default(monkeypatch):
    s = _settings(monkeypatch, ENVIRONMENT="development", RESEARCH_LEDGER_DIR=None)
    assert s.resolved_research_ledger_dir() == "data/research"


def test_development_with_an_explicit_value_uses_it_not_the_default(monkeypatch):
    s = _settings(monkeypatch, ENVIRONMENT="development", RESEARCH_LEDGER_DIR="/custom/path")
    assert s.resolved_research_ledger_dir() == "/custom/path"


def test_production_without_research_ledger_dir_resolves_to_none_not_the_local_default(monkeypatch):
    """The core production-safety fix: production/staging must NEVER fall
    back to a relative path that could silently be writable (and therefore
    falsely appear persistent) on Railway's own ephemeral filesystem."""
    s = _settings(monkeypatch, ENVIRONMENT="production", RESEARCH_LEDGER_DIR=None)
    assert s.resolved_research_ledger_dir() is None


def test_production_with_blank_research_ledger_dir_also_resolves_to_none(monkeypatch):
    s = _settings(monkeypatch, ENVIRONMENT="production", RESEARCH_LEDGER_DIR="   ")
    assert s.resolved_research_ledger_dir() is None


def test_production_with_an_explicit_research_ledger_dir_resolves_to_it(monkeypatch):
    s = _settings(monkeypatch, ENVIRONMENT="production", RESEARCH_LEDGER_DIR="/data/research")
    assert s.resolved_research_ledger_dir() == "/data/research"
