"""Standings must not silently come back empty when the upstream API hiccups.

Seen on Render: for years served by Jolpica (2025+), any failure of that API made the
Ergast service return its fallback — an empty list — and /api/drivers answered 200 [] . The
dashboard then showed "—" for the leader and an empty championship table until the tab was
reloaded.
"""
import asyncio

import pytest
from fastapi.responses import JSONResponse

import api.main as main

pytestmark = pytest.mark.asyncio

GOOD = [{"position": 1, "driver_id": "a", "driver_name": "A", "constructor": "X", "points": 10.0, "wins": 1, "nationality": "N"}]


class FakeCache:
    def __init__(self):
        self.store = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, data, ttl=3600):
        self.store[key] = data
        return True


class FakeErgast:
    """Async context manager like ErgastService; `script` is consumed one call at a time."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get_driver_standings(self, year, round=None, strict=False):
        assert strict is True, "the endpoint must ask for strict mode so failures aren't swallowed"
        self.calls += 1
        step = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(step, Exception):
            raise step
        return step


@pytest.fixture
def wired(monkeypatch):
    cache = FakeCache()
    monkeypatch.setattr(main, "cache_service", cache)
    monkeypatch.setattr(main, "STANDINGS_RETRY_DELAYS", (0.0, 0.0))
    monkeypatch.setattr(main, "_LAST_GOOD_STANDINGS", {})

    def use(script):
        ergast = FakeErgast(script)
        monkeypatch.setattr(main, "ergast_service", ergast)
        return ergast

    return cache, use


async def test_a_transient_failure_is_retried_and_the_good_result_is_cached(wired):
    cache, use = wired
    ergast = use([RuntimeError("HTTP 429"), RuntimeError("timeout"), GOOD])

    result = await main.legacy_driver_standings(year=2026, round=None, use_cache=True)

    assert result == GOOD and ergast.calls == 3
    assert cache.store["driver_standings_2026_current"] == GOOD


async def test_an_empty_answer_is_retried_too(wired):
    _, use = wired
    ergast = use([[], GOOD])

    assert await main.legacy_driver_standings(year=2026) == GOOD
    assert ergast.calls == 2


async def test_when_the_source_stays_down_the_last_good_copy_is_served(wired):
    _, use = wired
    use([GOOD])
    await main.legacy_driver_standings(year=2026, use_cache=False)     # remembers a good copy

    use([RuntimeError("HTTP 429")])                                    # ...then the source goes down
    result = await main.legacy_driver_standings(year=2026, use_cache=False)

    assert result == GOOD                                              # not [], not an error


async def test_a_transient_empty_answer_does_not_replace_the_last_good_copy(wired):
    _, use = wired
    use([GOOD])
    await main.legacy_driver_standings(year=2026, use_cache=False)

    use([[]])
    assert await main.legacy_driver_standings(year=2026, use_cache=False) == GOOD


async def test_with_no_copy_and_a_dead_source_it_is_a_clear_503_not_an_empty_200(wired):
    _, use = wired
    use([RuntimeError("HTTP 429")])

    result = await main.legacy_driver_standings(year=2026, use_cache=False)

    assert isinstance(result, JSONResponse) and result.status_code == 503
    assert b"source_unavailable" in result.body
    assert result.headers["retry-after"] == "10"


async def test_a_source_that_genuinely_has_no_standings_yet_is_still_an_empty_200(wired):
    _, use = wired
    use([[]])                                                          # answered fine, just nothing yet

    assert await main.legacy_driver_standings(year=2026, use_cache=False) == []


async def test_a_cached_answer_makes_no_upstream_call(wired):
    cache, use = wired
    cache.store["driver_standings_2026_current"] = GOOD
    ergast = use([RuntimeError("must not be called")])

    assert await main.legacy_driver_standings(year=2026) == GOOD
    assert ergast.calls == 0


async def test_constructors_get_the_same_protection(wired, monkeypatch):
    cache, _ = wired

    class C(FakeErgast):
        async def get_constructor_standings(self, year, round=None, strict=False):
            assert strict is True
            self.calls += 1
            if self.calls < 3:
                raise RuntimeError("HTTP 429")
            return [{"position": 1, "constructor_id": "x", "constructor_name": "X", "points": 5.0, "wins": 0, "nationality": "N"}]

    ergast = C([None])
    monkeypatch.setattr(main, "ergast_service", ergast)

    result = await main.legacy_constructor_standings(year=2026, use_cache=False)

    assert result[0]["constructor_name"] == "X" and ergast.calls == 3


async def test_a_hanging_upstream_is_not_retried_past_the_time_budget(wired, monkeypatch):
    _, use = wired
    ergast = use([RuntimeError("timeout")])
    monkeypatch.setattr(main, "STANDINGS_RETRY_BUDGET", 0.0)   # the first attempt already used it all

    result = await main.legacy_driver_standings(year=2026, use_cache=False)

    assert ergast.calls == 1
    assert isinstance(result, JSONResponse) and result.status_code == 503
