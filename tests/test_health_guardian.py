"""/health must notice a database that vanished underneath a running API.

The guardian only re-checks its connection on a timer, so before this check a project that was
paused while the API was awake kept reporting "ready" (and the frontend let visitors in) for
minutes — while every query was already failing. Now a failing probe triggers an immediate check.
"""
import pytest

import api.main as main
from services.db_guardian import CONNECTING, READY, DatabaseGuardian

pytestmark = pytest.mark.asyncio


class Db:
    def __init__(self, alive):
        self.alive = alive
        self.disconnects = 0

    async def connect(self):
        pass

    async def disconnect(self):
        self.disconnects += 1

    async def ping(self):
        return self.alive


class Service:
    """Stands in for SupabaseF1Service: _run_query swallows errors and returns [] on failure."""

    def __init__(self, working):
        self.working = working

    async def _run_query(self, query, params=None):
        return [{"probe": 1}] if self.working else []


def make_ready_guardian(db):
    g = DatabaseGuardian(db.connect, db.disconnect, db.ping, database_url="postgresql://x", min_attempt_gap=0)
    g.state = READY
    return g


@pytest.fixture
def wired(monkeypatch):
    async def redis_ok():
        return {"status": "ok", "kind": "mock", "info": {}}

    monkeypatch.setattr(main, "_probe_redis", redis_ok)
    yield monkeypatch


async def test_a_failing_probe_makes_health_verify_the_connection_and_drop_it(wired):
    db = Db(alive=False)                       # the project was paused: pings fail too
    g = make_ready_guardian(db)
    wired.setattr(main, "database_guardian", g)
    wired.setattr(main, "duckdb_service", Service(working=False))

    body = await main.health_check()

    assert body["checks"]["database"]["state"] == CONNECTING     # no longer claims "ready"
    assert body["checks"]["database"]["status"] != "ok"
    assert db.disconnects == 1
    assert body["status"] == "degraded"


async def test_a_one_off_probe_failure_with_a_working_connection_does_not_drop_it(wired):
    db = Db(alive=True)                        # probe returned [] once, but the connection is fine
    g = make_ready_guardian(db)
    wired.setattr(main, "database_guardian", g)
    wired.setattr(main, "duckdb_service", Service(working=False))

    body = await main.health_check()

    assert body["checks"]["database"]["state"] == READY
    assert db.disconnects == 0


async def test_a_healthy_database_is_not_pinged_by_health(wired):
    db = Db(alive=False)                       # would fail if it were pinged — it must not be
    g = make_ready_guardian(db)
    wired.setattr(main, "database_guardian", g)
    wired.setattr(main, "duckdb_service", Service(working=True))

    body = await main.health_check()

    assert body["checks"]["database"]["state"] == READY
    assert body["checks"]["database"]["can_restore"] is False    # no token configured in this test
    assert db.disconnects == 0
