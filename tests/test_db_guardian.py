"""DatabaseGuardian: wakes a paused Supabase project and keeps the DB connected.

Supabase's Management API is faked with httpx.MockTransport, so nothing here
touches the network or any real project.
"""
import asyncio
import json

import httpx
import pytest

from services.db_guardian import (
    CONNECTING, READY, UNAVAILABLE, WAKING, DatabaseGuardian,
)

pytestmark = pytest.mark.asyncio

REF = "abcdefghijklmnop"
URL = f"postgresql://postgres.{REF}:pw@aws-0-eu.pooler.supabase.com:6543/postgres"


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


class FakeDb:
    def __init__(self, fail_times=0):
        self.fail_times = fail_times
        self.connects = 0
        self.disconnects = 0
        self.alive = True

    async def connect(self):
        self.connects += 1
        if self.connects <= self.fail_times:
            raise ConnectionError("(ENOTFOUND) tenant/user postgres.x not found")

    async def disconnect(self):
        self.disconnects += 1

    async def ping(self):
        return self.alive


class FakeSupabase:
    """Scripted Management API: `statuses` is consumed one GET at a time (last one repeats)."""

    def __init__(self, statuses=(), get_code=200, restore_code=200):
        self.statuses = list(statuses)
        self.get_code = get_code
        self.restore_code = restore_code
        self.requests = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append((request.method, request.url.path, request.headers.get("authorization")))
        if request.method == "POST":
            return httpx.Response(self.restore_code, json={})
        if self.get_code != 200:
            return httpx.Response(self.get_code, json={})
        status = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
        return httpx.Response(200, json={"status": status})

    @property
    def posts(self):
        return [r for r in self.requests if r[0] == "POST"]

    @property
    def transport(self):
        return httpx.MockTransport(self.handler)


def make(db, api=None, token="tok", clock=None, **kw):
    kw.setdefault("min_attempt_gap", 0)
    return DatabaseGuardian(
        db.connect, db.disconnect, db.ping,
        database_url=URL, access_token=token,
        transport=api.transport if api else httpx.MockTransport(lambda r: pytest.fail("unexpected HTTP call")),
        clock=clock or Clock(), **kw,
    )


async def test_connects_first_time_without_touching_the_api():
    db = FakeDb()
    g = make(db)
    await g.attempt()
    assert g.state == READY and g.ready
    assert g.snapshot()["status"] == "ok"


async def test_project_ref_is_parsed_from_the_database_url():
    assert make(FakeDb()).project_ref == REF


async def test_without_a_token_it_only_reports_unavailable_and_never_calls_the_api():
    db = FakeDb(fail_times=5)
    g = make(db, token=None)
    await g.attempt()
    assert g.state == UNAVAILABLE
    assert not g.can_restore


async def test_paused_project_is_restored_once_then_reconnected():
    db = FakeDb(fail_times=2)
    api = FakeSupabase(["INACTIVE", "COMING_UP", "ACTIVE_HEALTHY"])
    clock = Clock()
    g = make(db, api, clock=clock)

    await g.attempt()                       # connect fails -> INACTIVE -> restore requested
    assert g.state == WAKING
    assert len(api.posts) == 1
    assert api.posts[0][1] == f"/v1/projects/{REF}/restore"
    assert api.requests[0][2] == "Bearer tok"

    clock.advance(15)
    await g.attempt()                       # still coming up: no second restore
    assert g.state == WAKING
    assert len(api.posts) == 1

    clock.advance(15)
    await g.attempt()                       # third connect succeeds
    assert g.state == READY
    assert len(api.posts) == 1


async def test_restore_is_not_repeated_inside_the_cooldown_but_is_after_it():
    db = FakeDb(fail_times=99)
    api = FakeSupabase(["INACTIVE"])
    clock = Clock()
    g = make(db, api, clock=clock, restore_cooldown=600)

    await g.attempt()
    clock.advance(60)
    await g.attempt()
    assert len(api.posts) == 1              # still cooling down

    clock.advance(600)
    await g.attempt()
    assert len(api.posts) == 2              # project went back to sleep or the restore was lost


async def test_a_rejected_token_is_reported_and_no_restore_is_attempted():
    db = FakeDb(fail_times=99)
    api = FakeSupabase(get_code=401)
    g = make(db, api)
    await g.attempt()
    assert g.state == UNAVAILABLE
    assert "rejected" in g.detail
    assert api.posts == []


async def test_management_api_outage_is_unavailable_not_waking():
    db = FakeDb(fail_times=99)
    api = FakeSupabase(get_code=500)
    g = make(db, api)
    await g.attempt()
    assert g.state == UNAVAILABLE and api.posts == []


async def test_active_project_with_failing_connection_is_unavailable_unless_just_restored():
    db = FakeDb(fail_times=99)
    api = FakeSupabase(["ACTIVE_HEALTHY"])
    g = make(db, api)
    await g.attempt()
    assert g.state == UNAVAILABLE           # nothing to wake — something else is wrong

    db2 = FakeDb(fail_times=99)
    api2 = FakeSupabase(["INACTIVE", "ACTIVE_HEALTHY"])
    clock = Clock()
    g2 = make(db2, api2, clock=clock)
    await g2.attempt()                      # INACTIVE -> restore
    clock.advance(15)
    await g2.attempt()                      # active now, but the pooler needs a few seconds
    assert g2.state == WAKING


async def test_attempts_closer_together_than_the_gap_are_skipped():
    db = FakeDb(fail_times=99)
    g = make(db, token=None, min_attempt_gap=5, clock=Clock())
    await g.attempt()
    await g.attempt()
    assert db.connects == 1


async def test_a_hanging_connect_times_out_instead_of_blocking_startup():
    async def hang():
        await asyncio.sleep(30)

    g = DatabaseGuardian(hang, FakeDb().disconnect, FakeDb().ping, database_url=URL,
                         connect_timeout=0.05, min_attempt_gap=0)
    await g.attempt()
    assert g.state == UNAVAILABLE


async def test_a_lost_connection_is_dropped_and_reestablished():
    db = FakeDb()
    g = make(db)
    await g.attempt()
    assert g.ready

    db.alive = False
    assert await g.check_alive() is False
    assert g.state == CONNECTING and db.disconnects == 1

    db.alive = True
    await g.attempt()
    assert g.ready and db.connects == 2


async def test_a_healthy_connection_stays_ready_on_keepalive():
    db = FakeDb()
    g = make(db)
    await g.attempt()
    assert await g.check_alive() is True
    assert g.ready and db.disconnects == 0


async def test_snapshot_never_leaks_the_token_or_project_ref():
    db = FakeDb(fail_times=99)
    api = FakeSupabase(["INACTIVE"])
    g = make(db, api, token="super-secret-token")
    await g.attempt()
    blob = json.dumps(g.snapshot())
    assert "super-secret-token" not in blob and REF not in blob and "ENOTFOUND" not in blob
    assert g.snapshot()["state"] == WAKING and g.snapshot()["message"]


async def test_background_loop_reconnects_on_its_own_and_stops_cleanly():
    db = FakeDb(fail_times=2)
    api = FakeSupabase(["INACTIVE", "ACTIVE_HEALTHY"])
    g = make(db, api, retry_seconds=0.01, keepalive_seconds=30)
    await g.start()                         # first attempt fails; loop takes over
    assert not g.ready

    for _ in range(200):
        if g.ready:
            break
        await asyncio.sleep(0.01)
    assert g.ready

    await g.stop()
    assert g._task is None


async def test_nudge_only_matters_while_the_database_is_down():
    db = FakeDb()
    g = make(db)
    g.nudge()
    assert g._nudge.is_set()                # still connecting: wake the retry loop now
    await g.attempt()
    g._nudge.clear()
    g.nudge()
    assert not g._nudge.is_set()            # ready: ignored


# --- added after live testing: why did the wake-up not work? ---------------------------------


async def test_a_project_that_is_pausing_is_watched_then_restored_once_paused():
    db = FakeDb(fail_times=99)
    api = FakeSupabase(["PAUSING", "PAUSING", "INACTIVE", "COMING_UP"])
    clock = Clock()
    g = make(db, api, clock=clock)

    await g.attempt()                       # still going down: nothing to restore yet
    assert g.state == WAKING and g.project_status == "PAUSING"
    assert api.posts == []

    clock.advance(15)
    await g.attempt()
    assert api.posts == []

    clock.advance(15)
    await g.attempt()                       # now fully paused -> restore
    assert g.project_status == "INACTIVE"
    assert len(api.posts) == 1


async def test_snapshot_says_whether_it_can_restore_and_what_supabase_reports():
    g = make(FakeDb(fail_times=99), FakeSupabase(["INACTIVE"]))
    assert g.snapshot()["can_restore"] is True
    await g.attempt()
    snap = g.snapshot()
    assert snap["project_status"] == "INACTIVE" and snap["state"] == WAKING

    no_token = make(FakeDb(fail_times=99), token=None)
    assert no_token.snapshot()["can_restore"] is False   # visible in /health, so a missing token is obvious


async def test_project_status_is_cleared_once_connected():
    db = FakeDb(fail_times=1)
    api = FakeSupabase(["INACTIVE", "ACTIVE_HEALTHY"])
    clock = Clock()
    g = make(db, api, clock=clock)
    await g.attempt()
    assert g.project_status == "INACTIVE"
    clock.advance(15)
    await g.attempt()
    assert g.ready and g.project_status is None


async def test_startup_is_not_held_up_by_a_database_that_never_answers():
    async def hang():
        await asyncio.sleep(30)

    g = DatabaseGuardian(hang, FakeDb().disconnect, FakeDb().ping, database_url=URL,
                         connect_timeout=30, min_attempt_gap=0)
    started = asyncio.get_running_loop().time()
    await g.start(initial_wait=0.1)         # would have blocked for the whole connect timeout before
    assert asyncio.get_running_loop().time() - started < 2
    assert not g.ready
    await g.stop()


async def test_a_lost_connection_is_noticed_and_reconnected_when_checked():
    db = FakeDb()
    api = FakeSupabase(["INACTIVE", "ACTIVE_HEALTHY"])
    clock = Clock()
    g = make(db, api, clock=clock)
    await g.attempt()
    assert g.ready

    db.alive = False                        # project paused underneath a running API
    db.fail_times = db.connects + 1         # next connect fails: it's really down
    assert await g.check_alive() is False
    assert g.state == CONNECTING

    await g.attempt()
    assert g.state == WAKING and len(api.posts) == 1   # noticed straight away, restore requested


# --- on_ready hook (used to warm the prediction models once the database is usable) ----------


async def test_on_ready_runs_when_the_database_becomes_ready_and_again_after_a_reconnect():
    calls = []

    async def hook():
        calls.append("ready")

    db = FakeDb()
    g = make(db, on_ready=hook)
    await g.attempt()
    await asyncio.sleep(0)                  # let the background task run
    assert calls == ["ready"]

    db.alive = False
    await g.check_alive()
    db.alive = True
    await g.attempt()
    await asyncio.sleep(0)
    assert calls == ["ready", "ready"]      # the hook itself is responsible for being a no-op when done


async def test_a_slow_on_ready_hook_does_not_delay_ready():
    started = asyncio.Event()

    async def slow_hook():
        started.set()
        await asyncio.sleep(30)

    g = make(FakeDb(), on_ready=slow_hook)
    await asyncio.wait_for(g.attempt(), timeout=1)   # returns immediately even though the hook runs 30s
    assert g.ready
    await asyncio.wait_for(started.wait(), timeout=1)
    await g.stop()                                   # cancels the hook instead of hanging
    await asyncio.sleep(0)
    assert not g._hooks


async def test_a_failing_on_ready_hook_does_not_break_the_connection():
    async def broken_hook():
        raise RuntimeError("training blew up")

    g = make(FakeDb(), on_ready=broken_hook)
    await g.attempt()
    await asyncio.sleep(0.01)
    assert g.ready
