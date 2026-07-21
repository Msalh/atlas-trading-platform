"""
Production-hardening: atlas.main's lifespan must never let an unexpected
exception raised by check_snapshots() take startup down with it - LIVE
endpoints (rule-engine/setup-engine) have zero dependency on the research
snapshot files and must keep working regardless. See
atlas/research_export/startup_check.py's own module docstring for the
"never block LIVE, never crash startup" contract this test proves for the
genuinely-unanticipated-exception case specifically (check_snapshots()
itself already turns every bad-file case it knows about into a normal
"invalid" result rather than raising - this covers the rare case of a bug
in that module raising something else).

Does not touch a real Postgres - create_pool is replaced with a fake, since
this test only needs to prove the try/except WRAPPING behavior around
check_snapshots(), not the rest of lifespan's startup sequence.
"""
import atlas.main as main_module
from atlas.research_export.startup_check import EXPECTED_SNAPSHOT_FILES


class _FakePool:
    async def close(self):
        pass


async def _fake_create_pool():
    return _FakePool()


def _raise_unexpected_error(_directory):
    raise RuntimeError("simulated unexpected failure inside check_snapshots, host=db.internal port=5432")


async def test_an_unexpected_check_snapshots_exception_does_not_fail_startup(monkeypatch):
    monkeypatch.setattr(main_module.settings, "environment", "development")
    monkeypatch.setattr(main_module, "create_pool", _fake_create_pool)
    monkeypatch.setattr(main_module, "check_snapshots", _raise_unexpected_error)

    app = main_module.app
    # If the try/except in lifespan() didn't catch this, entering this
    # context manager would itself raise and this test would fail with an
    # unhandled RuntimeError - the assertions below only run at all because
    # startup actually completed.
    async with main_module.lifespan(app):
        readiness = app.state.snapshots_readiness
        assert readiness.status == "invalid"
        assert readiness.reason == "internal_error"
        for filename in EXPECTED_SNAPSHOT_FILES:
            result = readiness.status_for(filename)  # KeyError here would mean FROZEN endpoints break too
            assert result.status == "invalid"
            assert result.reason == "internal_error"
            # FROZEN endpoints' _degraded_response (atlas/api/v1/research.py)
            # puts result.detail directly into the client-facing 503 body -
            # the raw exception text (and anything it might contain, like a
            # host/port) must never reach it.
            assert result.detail is not None
            assert "simulated unexpected failure" not in result.detail
            assert "db.internal" not in result.detail
            assert "5432" not in result.detail
