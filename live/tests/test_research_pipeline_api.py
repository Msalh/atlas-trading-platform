"""
Sprint 8.2. Tests for POST /api/v1/research/run and
GET /api/v1/research/leaderboard - the staging deployment's own smoke-test
and leaderboard-read endpoints. Exercises the client fixture's real,
tmp_path-backed LedgerStores (see tests/conftest.py's
ledger_readiness_and_stores fixture) - genuinely working stores, not a
hand-built fake, so these tests prove real persistence, not just that the
endpoint returns 200.
"""
from fastapi.testclient import TestClient

from atlas.api.deps import get_ledger_readiness, get_ledger_stores
from atlas.main import app
from atlas.research_deploy.startup_check import LedgerCheckResult, LedgerReadiness


def test_run_smoke_mode_succeeds_with_every_stage_stored(client):
    resp = client.post("/api/v1/research/run", json={"mode": "smoke"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["mode"] == "smoke"
    assert body["steps"] == {
        "realization_stored": True,
        "experiment_stored": True,
        "evidence_stored": True,
        "validation_stored": True,
        "leaderboard_snapshot_stored": True,
    }
    assert body["verdict"] == "supported"
    assert body["snapshot_id"]


def test_run_smoke_mode_snapshot_is_actually_readable_back(client):
    """The real proof of persistence, not just the endpoint's own claim:
    a completely separate GET request reads the same snapshot back."""
    run_resp = client.post("/api/v1/research/run", json={"mode": "smoke"})
    snapshot_id = run_resp.json()["snapshot_id"]

    leaderboard_resp = client.get(f"/api/v1/research/leaderboard?snapshot_id={snapshot_id}")
    assert leaderboard_resp.status_code == 200
    body = leaderboard_resp.json()
    assert body["ok"] is True
    assert body["snapshot_id"] == snapshot_id
    assert len(body["entries"]) == 1


def test_run_smoke_mode_repeated_calls_never_collide(client):
    """Each invocation uses a fresh, timestamped id - a real operational
    requirement (this endpoint gets called on every deploy verification),
    never a RecordConflictError from reusing a fixed id."""
    first = client.post("/api/v1/research/run", json={"mode": "smoke"})
    second = client.post("/api/v1/research/run", json={"mode": "smoke"})
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["snapshot_id"] != second.json()["snapshot_id"]


def test_run_unimplemented_modes_return_501_not_404_or_422(client):
    for mode in ("replay", "experiment", "benchmark"):
        resp = client.post("/api/v1/research/run", json={"mode": mode})
        assert resp.status_code == 501
        body = resp.json()
        assert body["ok"] is False
        assert mode in body["error"]


def test_run_invalid_mode_is_a_validation_error(client):
    resp = client.post("/api/v1/research/run", json={"mode": "not_a_real_mode"})
    assert resp.status_code == 422


def test_run_smoke_mode_fails_when_ledger_storage_is_degraded(client):
    app.dependency_overrides[get_ledger_readiness] = lambda: LedgerReadiness((
        LedgerCheckResult("configuration_valid", True, None),
        LedgerCheckResult("ledger_directory", False, "directory could not be created"),
        LedgerCheckResult("volume_mounted", False, "skipped - ledger_directory failed"),
        LedgerCheckResult("jsonl_stores_initialized", True, None),
        LedgerCheckResult("registries_available", False, "skipped - volume_mounted failed"),
    ))
    try:
        resp = client.post("/api/v1/research/run", json={"mode": "smoke"})
        assert resp.status_code == 503
        assert resp.json()["ok"] is False
    finally:
        app.dependency_overrides.pop(get_ledger_readiness, None)


def test_leaderboard_returns_404_when_nothing_recorded_yet(client):
    resp = client.get("/api/v1/research/leaderboard")
    assert resp.status_code == 404


def test_leaderboard_returns_404_for_an_unknown_snapshot_id(client):
    client.post("/api/v1/research/run", json={"mode": "smoke"})
    resp = client.get("/api/v1/research/leaderboard?snapshot_id=does-not-exist")
    assert resp.status_code == 404


def test_leaderboard_without_snapshot_id_returns_the_latest(client):
    first = client.post("/api/v1/research/run", json={"mode": "smoke"})
    second = client.post("/api/v1/research/run", json={"mode": "smoke"})
    resp = client.get("/api/v1/research/leaderboard")
    assert resp.status_code == 200
    assert resp.json()["snapshot_id"] == second.json()["snapshot_id"]
    assert first.json()["snapshot_id"] != resp.json()["snapshot_id"]


def test_research_run_requires_api_key_when_not_overridden():
    """Deliberately does not use the shared `client` fixture (which
    overrides require_api_key to a no-op) - mirrors tests/test_auth.py's
    own raw_client pattern exactly: TestClient(app) without the context-
    manager form never triggers the real Postgres-backed lifespan, and (as
    already proven for /api/v1/status and /api/v1/research/re1/summary in
    that file, neither of which override their own snapshots_readiness
    dependency either) require_api_key - a router-level dependency - short-
    circuits before this route's own per-parameter dependencies are ever
    resolved, so no ledger override is needed here either."""
    raw_client = TestClient(app)
    resp = raw_client.post("/api/v1/research/run", json={"mode": "smoke"})
    assert resp.status_code == 401


def test_ledger_stores_unavailable_returns_503_not_a_crash(client):
    """The rare internal_error_readiness() fallback case (see
    atlas.api.deps.get_ledger_stores's own docstring) - ledger_stores is
    None, and the route must degrade cleanly, never raise an
    AttributeError."""
    app.dependency_overrides[get_ledger_stores] = lambda: None
    try:
        resp = client.post("/api/v1/research/run", json={"mode": "smoke"})
        assert resp.status_code == 503
        assert resp.json()["ok"] is False
    finally:
        app.dependency_overrides.pop(get_ledger_stores, None)
