"""Each weekend's practice is loaded from OpenF1 as it finishes (services/weekend_practice.py).
OpenF1 is faked with httpx.MockTransport."""
from datetime import date, datetime, timezone

import httpx
import pandas as pd
import pytest

from services.openf1_live import OpenF1Client
from services.weekend_practice import (check_again_in, load_weekend_practice, team_id_for,
                                       weekends_to_check)

pytestmark = pytest.mark.asyncio

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)          # Saturday of the Singapore weekend
TEAMS = {"red_bull": "Red Bull Racing Honda RBPT", "mercedes": "Mercedes", "haas": "Haas F1 Team"}
DRIVERS = [{"driver_number": n, "name_acronym": code, "team_name": team, "full_name": name}
           for n, code, team, name in [(1, "VER", "Red Bull Racing", "Max VERSTAPPEN"), (12, "ANT", "Mercedes", "Kimi ANTONELLI"),
                                       (87, "BEA", "Haas F1 Team", "Oliver BEARMAN")] + [
               (100 + i, f"D{i:02d}", "Mercedes", f"Driver D{i:02d}") for i in range(10)]]


def laps():
    out = []
    for d in DRIVERS:
        base = {1: 90.0, 12: 90.5, 87: 91.0}.get(d["driver_number"], 92.0 + d["driver_number"] / 1000)
        out += [{"driver_number": d["driver_number"], "lap_duration": None, "is_pit_out_lap": True},
                {"driver_number": d["driver_number"], "lap_duration": base + 1, "is_pit_out_lap": False},
                {"driver_number": d["driver_number"], "lap_duration": base, "is_pit_out_lap": False}]
    return out


SESSIONS = [
    {"session_key": 1, "session_name": "Practice 1", "date_end": "2026-10-09T09:30:00+00:00"},
    {"session_key": 2, "session_name": "Practice 2", "date_end": "2026-10-09T14:00:00+00:00"},
    {"session_key": 3, "session_name": "Practice 3", "date_end": "2026-10-10T11:55:00+00:00"},   # ended 5 min ago
]


def openf1(calls, locked=False):
    def handler(request: httpx.Request) -> httpx.Response:
        name = request.url.path.rsplit("/", 1)[-1]
        calls.append(name)
        if locked:
            return httpx.Response(401, json={"detail": "Live F1 session in progress."})
        if name == "meetings":
            return httpx.Response(200, json=[
                {"meeting_key": 9, "meeting_name": "Singapore Grand Prix", "is_cancelled": True},     # a cancelled namesake
                {"meeting_key": 10, "meeting_name": "Singapore Grand Prix", "is_cancelled": False}])
        if name == "sessions":
            assert request.url.params["meeting_key"] == "10"
            return httpx.Response(200, json=SESSIONS)
        if name == "laps":
            return httpx.Response(200, json=laps())
        if name == "drivers":
            return httpx.Response(200, json=DRIVERS)
        return httpx.Response(404, json={"detail": "No results found."})
    return httpx.MockTransport(handler)


class FakeDb:
    def __init__(self, stored=()):
        self.results = {k: [{"driver_id": "x"}] for k in stored}
        self.drivers = []

    async def get_races_by_year(self, year):
        return [{"race_id": "2026_Singapore", "year": 2026, "round": 17, "gp": "Singapore", "date": "2026-10-11"},
                {"race_id": "2026_United States", "year": 2026, "round": 18, "gp": "United States", "date": "2026-10-25"}]

    async def get_race_results(self, race_id, session_type):
        return self.results.get((race_id, session_type), [])

    async def store_drivers(self, drivers, rename=False):
        assert rename is False
        self.drivers += drivers

    async def store_race_results(self, race_id, rows, session_type):
        self.results[(race_id, session_type)] = rows


def client(calls, **kw):
    return OpenF1Client(creds={}, per_minute=60000, transport=openf1(calls, **kw))


async def test_finished_practice_is_stored_like_fastf1s():
    db, calls = FakeDb(), []
    stored = await load_weekend_practice(db, client(calls), TEAMS, {}, now=NOW)

    # FP3 ended 5 minutes ago: left for the next check, while OpenF1 finishes publishing it
    assert stored == [{"race_id": "2026_Singapore", "session_type": "fp1"}, {"race_id": "2026_Singapore", "session_type": "fp2"}]
    rows = db.results[("2026_Singapore", "fp1")]
    ver = next(r for r in rows if r["driver_id"] == "ver")
    assert ver["position"] == 1 and ver["constructor_id"] == "red_bull"         # "Red Bull Racing" matched
    assert pd.to_timedelta(ver["time"]).total_seconds() == pytest.approx(90.0)  # best lap, not the out lap
    assert ver["laps_completed"] == 3 and ver["fastest_lap"] is True
    assert next(r for r in rows if r["driver_id"] == "bea")["constructor_id"] == "haas"
    assert {"driver_id": "ver", "full_name": "Max Verstappen", "number": 1} in db.drivers


async def test_sessions_already_stored_are_left_alone():
    db, calls = FakeDb(stored=[("2026_Singapore", "fp1"), ("2026_Singapore", "fp2"), ("2026_Singapore", "fp3")]), []
    assert await load_weekend_practice(db, client(calls), TEAMS, {}, now=NOW) == []
    assert calls == []


async def test_a_live_session_lock_stops_quietly():
    assert await load_weekend_practice(FakeDb(), client([], locked=True), TEAMS, {}, now=NOW) == []


async def test_only_weekends_around_today_are_checked():
    races = await FakeDb().get_races_by_year(2026)
    assert [r["round"] for r in weekends_to_check(races, date(2026, 10, 8))] == [17]
    assert weekends_to_check(races, date(2026, 10, 1)) == []
    assert check_again_in(races, date(2026, 10, 9)) == 20 * 60 and check_again_in(races, date(2026, 10, 15)) == 6 * 3600


async def test_team_names_match_despite_suffixes_but_not_ambiguously():
    assert team_id_for("Red Bull Racing", TEAMS) == "red_bull"
    assert team_id_for("Haas", TEAMS) == "haas"
    assert team_id_for("Racing Bulls", TEAMS) is None
    assert team_id_for("Red Bull", {"a": "Red Bull Racing", "b": "Red Bull Junior"}) is None
