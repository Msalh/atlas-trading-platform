"""
Tests for rate limiting (Sprint 9) - atlas/rate_limit.py, applied via
@limiter.limit(...) on POST /webhook (30/minute) and POST /ai/reports/{period}
(5/minute). Closes the Sprint 8 audit finding that the AI report trigger was an
unauthenticated, unbounded, real-money (Anthropic billing) cost vector.

These deliberately drive the limiter past its threshold within a single test, then
rely on tests/conftest.py's autouse `_reset_rate_limiter` fixture to reset the shared
in-memory counters before the next test runs, so exceeding a limit here can't cause an
unrelated test elsewhere in the suite to fail.
"""
from unittest.mock import patch

import atlas.ai as ai_module
from atlas.api.v1 import webhook
from tests.conftest import entry_payload


def test_webhook_rate_limit_allows_traffic_under_the_threshold(client):
    with patch.object(webhook, "forward_to_pickmytrade", return_value=(True, 200, None)), \
         patch.object(ai_module, "analyze_with_claude"):
        for i in range(5):
            resp = client.post("/webhook", json=entry_payload(f"corr-rl-ok-{i}"))
            assert resp.status_code in (200, 207)


def test_webhook_rate_limit_returns_429_once_exceeded(client):
    with patch.object(webhook, "forward_to_pickmytrade", return_value=(True, 200, None)), \
         patch.object(ai_module, "analyze_with_claude"):
        statuses = [
            client.post("/webhook", json=entry_payload(f"corr-rl-{i}")).status_code
            for i in range(35)  # limit is 30/minute
        ]
    assert 429 in statuses


def test_ai_report_trigger_rate_limit_returns_429_once_exceeded(client):
    """The report-trigger endpoint's limit (5/minute) is much tighter than the
    webhook's - it's the one endpoint in this system that costs real money per call."""
    with patch.object(ai_module, "analyze_with_claude", return_value=("Report text.", None)):
        statuses = [client.post("/api/v1/ai/reports/daily").status_code for _ in range(8)]
    assert 429 in statuses


def test_rate_limit_is_reset_between_tests(client):
    """Sanity check for the autouse limiter-reset fixture itself - if the previous
    tests' request counts leaked into this one, a single request could already be
    rate-limited here, which would silently mask a real regression in the fixture."""
    with patch.object(webhook, "forward_to_pickmytrade", return_value=(True, 200, None)), \
         patch.object(ai_module, "analyze_with_claude"):
        resp = client.post("/webhook", json=entry_payload("corr-fresh-slate"))
    assert resp.status_code in (200, 207)
