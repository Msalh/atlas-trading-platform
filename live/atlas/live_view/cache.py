"""
UI v2, amendment 4. A small, bounded, in-process cache for
build_live_window_result()'s output.

Correctness claim, precisely scoped (never stated as unconditional - the
amendment's own requirement): the cache key is
(symbol, timeframe, window, latest_bar_timestamp,
 rule_engine_registry_fingerprint, setup_engine_registry_fingerprint).
Because the ONLY thing that can change the pipeline's result for a fixed
(symbol, timeframe, window) under an UNCHANGED registry is a new closed
bar arriving, keying on the latest bar's own timestamp makes an entry
correct for as long as that key doesn't change - no TTL is needed to
invalidate on a NEW bar. The registry fingerprints (a hash over each
registry's own (name, definition_version) pairs) additionally protect
against silently serving a stale result across a code-version mismatch in
a hypothetical multi-process deployment; in the single-process deployment
this project runs today, REGISTRY is a module-level constant fixed at
process start, so this can only actually change on a restart, which
already clears this in-process cache - a correctness-by-construction
addition, not a fix for an observed failure mode.

What this key CANNOT detect: a backfill or correction to a bar INSIDE the
window that is not the LATEST bar. This project's repository layer
(atlas.market_engine.ports.MarketStateRepository) has no data-revision or
last-modified marker today (get_latest/get_history/get_range/ingest/ping -
no version field) to fold into the key instead. The TTL below exists
specifically to bound this one residual gap - a documented limitation, not
an unconditional guarantee. If a repository revision marker is ever added,
it should be folded into the cache key and this TTL requirement
reconsidered (architecture doc §9, implementation plan §6).
"""
import hashlib
import time
from typing import Optional

from atlas.live_view.models import LiveWindowResult
from atlas.rule_engine.registry import REGISTRY as RULE_ENGINE_REGISTRY
from atlas.setup_engine.registry import REGISTRY as SETUP_ENGINE_REGISTRY

DEFAULT_MAX_ENTRIES = 32
DEFAULT_TTL_SECONDS = 60.0


def _registry_fingerprint(registry) -> str:
    pairs = sorted((r.name, r.definition.version) for r in registry)
    return hashlib.sha256(repr(pairs).encode("utf-8")).hexdigest()[:16]


def rule_engine_registry_fingerprint() -> str:
    return _registry_fingerprint(RULE_ENGINE_REGISTRY)


def setup_engine_registry_fingerprint() -> str:
    return _registry_fingerprint(SETUP_ENGINE_REGISTRY)


CacheKey = tuple[str, str, int, str, str, str]


def build_cache_key(symbol: str, timeframe: str, window: int, latest_bar_timestamp: str) -> CacheKey:
    return (
        symbol, timeframe, window, latest_bar_timestamp,
        rule_engine_registry_fingerprint(), setup_engine_registry_fingerprint(),
    )


class LiveWindowCache:
    """Bounded LRU with a TTL safety net - see module docstring for the
    precise, deliberately-not-unconditional correctness claim. Not
    thread-safe beyond Python's own GIL-serialized dict operations; this
    project's async routes run single-process, single-event-loop, so no
    additional locking is needed (in-flight coalescing, a distinct
    concern, is handled by the caller via an asyncio.Lock per key - see
    atlas/api/v1/setup_engine.py)."""

    def __init__(self, max_entries: int = DEFAULT_MAX_ENTRIES, ttl_seconds: float = DEFAULT_TTL_SECONDS) -> None:
        self._max_entries = max_entries
        self._ttl_seconds = ttl_seconds
        self._entries: dict[CacheKey, tuple[float, LiveWindowResult]] = {}
        self._order: list[CacheKey] = []  # least-recently-USED first (a hit promotes to the end - see get())

    def get(self, key: CacheKey) -> Optional[LiveWindowResult]:
        entry = self._entries.get(key)
        if entry is None:
            return None
        inserted_at, result = entry
        if time.monotonic() - inserted_at > self._ttl_seconds:
            self._evict(key)
            return None
        # Production-hardening amendment 6: promote on hit - this is what
        # actually makes it LRU rather than FIFO-by-insertion. Before this,
        # a key accessed on every request could still be evicted first
        # simply for being the oldest *inserted* entry, contradicting this
        # class's own docstring, which already claimed "Bounded LRU."
        self._order.remove(key)
        self._order.append(key)
        return result

    def put(self, key: CacheKey, result: LiveWindowResult) -> None:
        if key in self._entries:
            self._order.remove(key)
        self._entries[key] = (time.monotonic(), result)
        self._order.append(key)
        while len(self._order) > self._max_entries:
            oldest = self._order[0]
            self._evict(oldest)

    def _evict(self, key: CacheKey) -> None:
        self._entries.pop(key, None)
        if key in self._order:
            self._order.remove(key)

    def invalidate_all(self) -> None:
        """Exposed for any future in-process caller (e.g. a correction
        tool running inside the same server process) - no HTTP admin
        endpoint wraps this today; a process restart remains the primary
        invalidation path (architecture doc §9)."""
        self._entries.clear()
        self._order.clear()

    def __len__(self) -> int:
        return len(self._entries)
