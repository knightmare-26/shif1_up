"""The free server sleeps between visits, so whatever data upkeep and the results refresh missed is
caught up the moment it starts — not after fixed delays a short visit never outlasts (data upkeep
used to wait 2 minutes, then an hour if the database wasn't connected yet; the results refresh 10
minutes). The services are faked; only the loops' timing is tested."""
import asyncio

import pytest

import api.main as main

pytestmark = pytest.mark.asyncio


class Guardian:
    ready = False


class Report:
    needs_retrain = False

    def summary(self):
        return "nothing to do"


class Db:
    async def get_races_by_year(self, year):
        return []


@pytest.fixture
def loops(monkeypatch):
    calls, guardian = [], Guardian()

    async def ensure_trained(db):
        calls.append("models")

    async def weekend(*args, **kwargs):
        calls.append("weekend sessions")
        return []

    async def testing(*args, **kwargs):
        return False

    async def upkeep(*args, **kwargs):
        calls.append("data upkeep")
        return Report()

    async def refresh(db, days):
        calls.append("results refresh")
        return []

    monkeypatch.setattr(main, "duckdb_service", Db())
    monkeypatch.setattr(main, "database_guardian", guardian)
    monkeypatch.setattr(main.prediction_service, "_ensure_trained", ensure_trained)
    monkeypatch.setattr(main, "load_weekend_practice", weekend)
    monkeypatch.setattr(main.preseason_testing, "refresh", testing)
    monkeypatch.setattr(main.data_upkeep, "run", upkeep)
    monkeypatch.setattr(main.ingest_service, "refresh_recent_results", refresh)
    monkeypatch.setattr(main.ingest_service, "status", {"running": False})
    monkeypatch.setattr(main, "_last_teams", lambda: {})
    monkeypatch.setattr(main, "DATA_UPKEEP_FIRST_DELAY", 0)
    monkeypatch.setattr(main, "DATA_UPKEEP_NOT_READY", 0.01)
    monkeypatch.setattr(main, "_startup_upkeep", asyncio.Event())
    tasks = []
    yield calls, guardian, tasks
    for task in tasks:
        task.cancel()


async def until(condition, timeout=2.0):
    for _ in range(int(timeout / 0.01)):
        if condition():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("timed out")


async def test_upkeep_catches_up_as_soon_as_the_database_connects(loops):
    calls, guardian, tasks = loops
    tasks.append(asyncio.create_task(main._data_upkeep_loop()))
    await asyncio.sleep(0.05)
    assert calls == []                      # still connecting (a paused project waking): look again shortly

    guardian.ready = True
    await asyncio.wait_for(main._startup_upkeep.wait(), timeout=2)
    assert calls == ["models", "weekend sessions", "data upkeep"]


async def test_the_results_refresh_follows_the_first_upkeep_pass_straight_away(loops):
    calls, guardian, tasks = loops
    guardian.ready = True
    tasks.append(asyncio.create_task(main._results_refresh_loop()))
    await asyncio.sleep(0.05)
    assert calls == []                      # not alongside upkeep: one heavy batch at a time

    tasks.append(asyncio.create_task(main._data_upkeep_loop()))
    await until(lambda: "results refresh" in calls)
    assert calls == ["models", "weekend sessions", "data upkeep", "results refresh"]


async def test_a_failed_upkeep_pass_doesnt_hold_the_results_refresh_back(loops, monkeypatch):
    calls, guardian, tasks = loops
    guardian.ready = True

    async def broken(*args, **kwargs):
        raise RuntimeError("OpenF1 is having a day")
    monkeypatch.setattr(main, "load_weekend_practice", broken)

    tasks += [asyncio.create_task(main._results_refresh_loop()), asyncio.create_task(main._data_upkeep_loop())]
    await until(lambda: "results refresh" in calls)
