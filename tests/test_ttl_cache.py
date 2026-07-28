"""Tests for firebird_service.TTLCache — the single-flight/TTL layer in front
of the slow Firebird report queries, and the stale fallback the masters works
endpoint answers with when a fresh query misses the request deadline."""
import threading
import time

from app.services.firebird_service import TTLCache


def test_second_call_within_ttl_does_not_recompute():
    calls = []
    cache = TTLCache(ttl=60)
    for _ in range(3):
        cache.get_or_compute("k", lambda: calls.append(1) or "value")
    assert len(calls) == 1


def test_value_is_recomputed_after_the_ttl_lapses():
    calls = []
    cache = TTLCache(ttl=0.05)
    cache.get_or_compute("k", lambda: calls.append(1) or "a")
    time.sleep(0.08)
    cache.get_or_compute("k", lambda: calls.append(1) or "b")
    assert len(calls) == 2


def test_distinct_keys_are_independent():
    cache = TTLCache(ttl=60)
    assert cache.get_or_compute("a", lambda: 1) == 1
    assert cache.get_or_compute("b", lambda: 2) == 2
    assert cache.get_or_compute("a", lambda: 99) == 1


def test_concurrent_callers_share_one_computation():
    """The whole point: a burst of identical requests must become one
    Firebird round trip, not N."""
    calls = []
    started = threading.Event()
    cache = TTLCache(ttl=60)

    def slow():
        calls.append(1)
        started.set()
        time.sleep(0.15)
        return "value"

    results = []
    threads = [threading.Thread(target=lambda: results.append(cache.get_or_compute("k", slow)))
               for _ in range(5)]
    threads[0].start()
    started.wait(timeout=2)
    for t in threads[1:]:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert len(calls) == 1
    assert results == ["value"] * 5


def test_a_failed_computation_is_not_cached():
    cache = TTLCache(ttl=60)
    try:
        cache.get_or_compute("k", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    except RuntimeError:
        pass
    assert cache.get_or_compute("k", lambda: "recovered") == "recovered"


# --- stale fallback -------------------------------------------------------

def test_get_stale_returns_nothing_for_an_unknown_key():
    assert TTLCache(ttl=60).get_stale("never-computed") is None


def test_get_stale_returns_the_value_after_the_ttl_lapses():
    """An expired entry has to survive: it is what the endpoint answers with
    when a fresh query cannot finish inside the request budget."""
    cache = TTLCache(ttl=0.05)
    cache.get_or_compute("k", lambda: "value")
    time.sleep(0.08)
    # confirm it really is expired for normal reads
    assert cache.get_or_compute("k", lambda: "recomputed") == "recomputed"

    cache2 = TTLCache(ttl=0.05)
    cache2.get_or_compute("k", lambda: "value")
    time.sleep(0.08)
    stale = cache2.get_stale("k")
    assert stale is not None
    value, age = stale
    assert value == "value"
    # Only that the age is real and past the TTL -- an exact bound would be
    # flaky, since a sleep can return a hair early on a coarse clock.
    assert age > 0.04


def test_get_stale_reports_a_growing_age():
    cache = TTLCache(ttl=60)
    cache.get_or_compute("k", lambda: "value")
    _v, first = cache.get_stale("k")
    time.sleep(0.05)
    _v, later = cache.get_stale("k")
    assert later > first


def test_cache_is_bounded_and_evicts_the_oldest():
    """Each entry is a whole report and the keys are user-chosen date ranges,
    so retention has to be capped or the map only ever grows."""
    cache = TTLCache(ttl=60, max_entries=3)
    for i in range(5):
        cache.get_or_compute(f"k{i}", lambda i=i: i)
        time.sleep(0.005)  # keep stored_at strictly ordered
    assert cache.get_stale("k0") is None
    assert cache.get_stale("k1") is None
    assert cache.get_stale("k4") is not None
    assert cache.get_stale("k4")[0] == 4


def test_waiters_do_not_receive_a_stale_value_as_if_it_were_fresh():
    """A waiter releases only when the owner finishes. If the owner failed,
    the only entry present may be an expired one from an earlier round --
    returning that silently would hand back old data as current."""
    cache = TTLCache(ttl=0.05)
    cache.get_or_compute("k", lambda: "old")
    time.sleep(0.08)

    seen = []

    def failing():
        time.sleep(0.1)
        raise RuntimeError("firebird busy")

    def waiter():
        try:
            seen.append(cache.get_or_compute("k", lambda: "fresh"))
        except RuntimeError:
            seen.append("raised")

    def run_owner():
        try:
            cache.get_or_compute("k", failing)
        except RuntimeError:
            pass  # expected: this is the failure the waiter has to survive

    owner = threading.Thread(target=run_owner)
    owner.start()
    time.sleep(0.02)
    w = threading.Thread(target=waiter)
    w.start()
    owner.join(timeout=5)
    w.join(timeout=5)

    assert "old" not in seen, "waiter was handed an expired value as if fresh"
