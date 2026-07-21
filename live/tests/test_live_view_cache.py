"""
UI v2, amendment 4. Tests for atlas.live_view.cache - the bar-and-registry-
fingerprint-keyed cache with a documented, bounded TTL (never claimed as
an unconditional correctness guarantee - see that module's own docstring).
"""
import time

from atlas.live_view.cache import (
    LiveWindowCache,
    build_cache_key,
    rule_engine_registry_fingerprint,
    setup_engine_registry_fingerprint,
)

_DUMMY_RESULT_A = object()
_DUMMY_RESULT_B = object()


class TestCacheKey:
    def test_same_inputs_produce_the_same_key(self):
        key_1 = build_cache_key("MNQ1!", "5m", 500, "2026-07-20T14:35:00+00:00")
        key_2 = build_cache_key("MNQ1!", "5m", 500, "2026-07-20T14:35:00+00:00")
        assert key_1 == key_2

    def test_a_new_latest_bar_timestamp_changes_the_key(self):
        key_1 = build_cache_key("MNQ1!", "5m", 500, "2026-07-20T14:35:00+00:00")
        key_2 = build_cache_key("MNQ1!", "5m", 500, "2026-07-20T14:40:00+00:00")
        assert key_1 != key_2

    def test_a_different_window_changes_the_key(self):
        key_1 = build_cache_key("MNQ1!", "5m", 500, "2026-07-20T14:35:00+00:00")
        key_2 = build_cache_key("MNQ1!", "5m", 1000, "2026-07-20T14:35:00+00:00")
        assert key_1 != key_2

    def test_registry_fingerprints_are_deterministic(self):
        assert rule_engine_registry_fingerprint() == rule_engine_registry_fingerprint()
        assert setup_engine_registry_fingerprint() == setup_engine_registry_fingerprint()

    def test_registry_fingerprints_are_included_in_the_key(self):
        key = build_cache_key("MNQ1!", "5m", 500, "2026-07-20T14:35:00+00:00")
        assert rule_engine_registry_fingerprint() in key
        assert setup_engine_registry_fingerprint() in key


class TestCacheHitMiss:
    def test_miss_on_first_lookup(self):
        cache = LiveWindowCache()
        key = build_cache_key("MNQ1!", "5m", 500, "2026-07-20T14:35:00+00:00")
        assert cache.get(key) is None

    def test_hit_after_put(self):
        cache = LiveWindowCache()
        key = build_cache_key("MNQ1!", "5m", 500, "2026-07-20T14:35:00+00:00")
        cache.put(key, _DUMMY_RESULT_A)
        assert cache.get(key) is _DUMMY_RESULT_A

    def test_a_new_bar_timestamp_is_a_genuine_miss_not_the_stale_entry(self):
        cache = LiveWindowCache()
        key_old = build_cache_key("MNQ1!", "5m", 500, "2026-07-20T14:35:00+00:00")
        key_new = build_cache_key("MNQ1!", "5m", 500, "2026-07-20T14:40:00+00:00")
        cache.put(key_old, _DUMMY_RESULT_A)
        assert cache.get(key_new) is None


class TestTTL:
    def test_entry_expires_after_ttl(self):
        cache = LiveWindowCache(ttl_seconds=0.05)
        key = build_cache_key("MNQ1!", "5m", 500, "2026-07-20T14:35:00+00:00")
        cache.put(key, _DUMMY_RESULT_A)
        assert cache.get(key) is _DUMMY_RESULT_A
        time.sleep(0.08)
        assert cache.get(key) is None

    def test_expired_entry_is_actually_evicted_not_just_hidden(self):
        cache = LiveWindowCache(ttl_seconds=0.05, max_entries=1)
        key = build_cache_key("MNQ1!", "5m", 500, "2026-07-20T14:35:00+00:00")
        cache.put(key, _DUMMY_RESULT_A)
        time.sleep(0.08)
        cache.get(key)  # triggers eviction as a side effect
        assert len(cache) == 0


class TestLRUEviction:
    def test_oldest_entry_evicted_when_over_capacity(self):
        cache = LiveWindowCache(max_entries=2)
        key_1 = build_cache_key("MNQ1!", "5m", 500, "2026-07-20T14:00:00+00:00")
        key_2 = build_cache_key("MNQ1!", "5m", 500, "2026-07-20T14:05:00+00:00")
        key_3 = build_cache_key("MNQ1!", "5m", 500, "2026-07-20T14:10:00+00:00")
        cache.put(key_1, _DUMMY_RESULT_A)
        cache.put(key_2, _DUMMY_RESULT_B)
        cache.put(key_3, _DUMMY_RESULT_A)
        assert len(cache) == 2
        assert cache.get(key_1) is None  # evicted, oldest
        assert cache.get(key_2) is _DUMMY_RESULT_B
        assert cache.get(key_3) is _DUMMY_RESULT_A

    def test_re_putting_an_existing_key_does_not_grow_the_cache(self):
        cache = LiveWindowCache(max_entries=2)
        key = build_cache_key("MNQ1!", "5m", 500, "2026-07-20T14:00:00+00:00")
        cache.put(key, _DUMMY_RESULT_A)
        cache.put(key, _DUMMY_RESULT_B)
        assert len(cache) == 1
        assert cache.get(key) is _DUMMY_RESULT_B

    def test_a_hit_promotes_the_entry_so_it_survives_an_eviction_round_fifo_would_have_dropped_it_for(self):
        """Production-hardening amendment 6. This is the one case that
        distinguishes true LRU from FIFO-by-insertion: key_1 is the oldest
        *inserted* entry, but it is read (a hit) right before key_3 is
        added - under plain FIFO that read has no effect and key_1 would
        still be evicted next; under real LRU, that read makes key_2 the
        least-recently-used one instead, so key_2 is evicted and key_1
        survives."""
        cache = LiveWindowCache(max_entries=2)
        key_1 = build_cache_key("MNQ1!", "5m", 500, "2026-07-20T14:00:00+00:00")
        key_2 = build_cache_key("MNQ1!", "5m", 500, "2026-07-20T14:05:00+00:00")
        key_3 = build_cache_key("MNQ1!", "5m", 500, "2026-07-20T14:10:00+00:00")

        cache.put(key_1, _DUMMY_RESULT_A)
        cache.put(key_2, _DUMMY_RESULT_B)
        assert cache.get(key_1) is _DUMMY_RESULT_A  # promotes key_1 to most-recently-used
        cache.put(key_3, _DUMMY_RESULT_A)  # over capacity - evicts the least-recently-used, key_2

        assert len(cache) == 2
        assert cache.get(key_1) is _DUMMY_RESULT_A  # survived - it was used, not just old
        assert cache.get(key_2) is None  # evicted - never touched after being inserted
        assert cache.get(key_3) is _DUMMY_RESULT_A


class TestInvalidateAll:
    def test_clears_every_entry(self):
        cache = LiveWindowCache()
        key = build_cache_key("MNQ1!", "5m", 500, "2026-07-20T14:35:00+00:00")
        cache.put(key, _DUMMY_RESULT_A)
        cache.invalidate_all()
        assert cache.get(key) is None
        assert len(cache) == 0
