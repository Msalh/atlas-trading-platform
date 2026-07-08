"""
Rate limiting (Sprint 9), via slowapi (in-memory, per-process - consistent with the
rest of this codebase's already-documented single-instance assumption; see
atlas/events/bus.py's docstring for the same seam). Keyed by remote IP address, which
is adequate for a single-user tool behind no load balancer/proxy that would hide the
real client IP.

`limiter.reset()` clears all counters - used by tests/conftest.py's autouse fixture so
one test's requests can never push another test over a limit.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

# A generous baseline covers the dashboard's own polling (multiple GETs every few
# seconds across ~10 endpoints) while still bounding abuse of an authenticated
# endpoint (e.g. a leaked/guessed API key being hammered). Specific endpoints with a
# tighter, more meaningful limit (webhook, AI report triggers) declare their own via
# @limiter.limit(...) - see atlas/api/v1/webhook.py and atlas/api/v1/ai.py.
DEFAULT_LIMITS = ["200/minute"]

limiter = Limiter(key_func=get_remote_address, default_limits=DEFAULT_LIMITS)
