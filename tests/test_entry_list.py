"""Predictions cover who's actually entered for the weekend (services/entry_list.py and the
field handling in PredictionService). OpenF1 is faked with httpx.MockTransport."""
from datetime import datetime, timedelta, timezone

import httpx
import numpy as np
import pandas as pd
import pytest

from services.entry_list import EntryListService
from services.openf1_live import OpenF1Client
from services.prediction_service import PredictionService

NOW = datetime.now(timezone.utc)


def iso(hours: float) -> str:
    return (NOW + timedelta(hours=hours)).isoformat()


class FakeDb:
    def __init__(self, sessions):
        self.sessions = sessions          # session_type -> [(driver_id, constructor_id)]

    async def get_races_by_year(self, year):
        return [{"race_id": "2026_Azerbaijan", "round": 15, "circuit_name": "Baku"}]

    async def get_race_results(self, race_id, session_type):
        return [{"driver_id": d, "constructor_id": c} for d, c in self.sessions.get(session_type, [])]


def grid(n=20, team="", skip=(), extra=()):
    rows = [(f"d{i:02d}", team or f"t{i % 10}") for i in range(n) if f"d{i:02d}" not in skip]
    return rows + list(extra)


OPENF1_DRIVERS = [{"name_acronym": f"D{i:02d}", "team_name": f"Team {i % 10}", "full_name": f"Driver {i:02d}"} for i in range(20)]


def fake_openf1(calls, locked=False, drivers=OPENF1_DRIVERS):
    def handler(request: httpx.Request) -> httpx.Response:
        name = request.url.path.rsplit("/", 1)[-1]
        calls.append((name, dict(request.url.params)))
        if locked:
            return httpx.Response(401, json={"detail": "Live F1 session in progress."})
        if name == "meetings":
            return httpx.Response(200, json=[{"meeting_key": 1, "location": "Baku", "date_start": iso(-30)},
                                             {"meeting_key": 2, "location": "Marina Bay", "date_start": iso(200)}])
        if name == "sessions":
            return httpx.Response(200, json=[
                {"session_key": 11, "session_name": "Practice 1", "date_start": iso(-30)},
                {"session_key": 12, "session_name": "Practice 2", "date_start": iso(-26)},
                {"session_key": 13, "session_name": "Qualifying", "date_start": iso(20)},    # not started
            ])
        if name == "drivers":
            return httpx.Response(200, json=drivers)
        return httpx.Response(404, json={"detail": "No results found."})
    return httpx.MockTransport(handler)


def service(calls, **kw):
    return EntryListService(lambda: OpenF1Client(creds={}, per_minute=60000, transport=fake_openf1(calls, **kw)))


TEAMS = {f"t{i}": f"Team {i}" for i in range(10)}


@pytest.mark.asyncio
async def test_stored_qualifying_beats_practice_and_needs_no_openf1():
    calls = []
    db = FakeDb({"fp2": grid(skip=("d05",)), "qualifying": grid()})
    field = await service(calls).field(db, "Baku", 2026, TEAMS)

    assert field.source == "this weekend's qualifying" and len(field.teams) == 20 and calls == []


@pytest.mark.asyncio
async def test_practice_1_is_only_a_last_resort():
    db = FakeDb({"fp1": grid(extra=[("rookie", "t1")]), "fp2": grid()})
    assert (await service([]).field(db, "Baku", 2026, TEAMS)).source == "this weekend's practice 2"


@pytest.mark.asyncio
async def test_missing_teams_in_stored_practice_are_filled_from_openf1():
    db = FakeDb({"fp2": grid(team="-")})
    db.sessions["fp2"] = [(d, "") for d, _ in db.sessions["fp2"]]      # FastF1 gave no team
    field = await service([]).field(db, "Baku", 2026, TEAMS)

    assert field.source == "this weekend's practice 2"
    assert field.teams["d03"] == "t3" and field.names["d03"] == "Driver 03"


@pytest.mark.asyncio
async def test_openf1_uses_the_latest_started_session_that_is_not_practice_1():
    calls = []
    field = await service(calls).field(FakeDb({}), "Baku", 2026, TEAMS)

    assert field.source == "the practice 2 entry list" and len(field.teams) == 20
    assert ("drivers", {"session_key": "12"}) in calls


@pytest.mark.asyncio
async def test_nothing_known_yet_or_openf1_locked_means_no_field():
    assert await service([], locked=True).field(FakeDb({}), "Baku", 2026, TEAMS) is None
    assert await service([], drivers=OPENF1_DRIVERS[:5]).field(FakeDb({}), "Baku", 2026, TEAMS) is None   # not a whole field


# --- the model side ------------------------------------------------------------------------------

def history():
    rows = []
    for rnd in range(1, 6):
        for i, (d, team) in enumerate([("aaa", "fast"), ("bbb", "fast"), ("ccc", "slow"), ("ddd", "slow")]):
            if d == "ddd" and rnd > 3:
                continue                      # ddd is out (injured) for the last two rounds
            rows.append({"year": 2026, "round": rnd, "race_id": f"r{rnd}", "circuit_name": "Baku" if rnd == 1 else f"c{rnd}",
                         "driver_id": d, "constructor_id": team, "position": i + 1, "grid": i + 1,
                         "driver_rolling_finish": i + 1.0, "driver_rolling_grid": i + 1.0,
                         "constructor_rolling_finish": 1.5 if team == "fast" else 3.5, "driver_dnf_rate": 0.1})
    return pd.DataFrame(rows)


def test_the_field_brings_back_a_returning_driver_and_drops_an_absent_one():
    svc = PredictionService(model_dir="unused")
    svc._df = history()

    default = svc._build_prediction_rows("Baku")
    entered = svc._build_prediction_rows("Baku", field={"aaa": None, "ccc": None, "ddd": "slow", "new": "fast"})

    assert set(default["driver_id"]) == {"aaa", "bbb", "ccc"}              # last race: ddd missing
    assert set(entered["driver_id"]) == {"aaa", "ccc", "ddd", "new"}        # bbb not entered
    debut = entered.set_index("driver_id").loc["new"]
    assert debut["constructor_id"] == "fast" and debut["constructor_rolling_finish"] == 1.5   # the team's form
    assert not np.isnan(debut["driver_rolling_finish"])


def test_a_driver_in_a_different_car_gets_that_teams_form():
    svc = PredictionService(model_dir="unused")
    svc._df = history()

    rows = svc._build_prediction_rows("Baku", field={"ccc": "fast"}).set_index("driver_id")

    assert rows.loc["ccc", "constructor_id"] == "fast" and rows.loc["ccc", "constructor_rolling_finish"] == 1.5


def test_a_cached_prediction_is_reused_only_for_the_same_drivers_in_the_same_cars():
    cached = {"model_trained_at": "t", "result": {"field_source": "x", "predictions": [
        {"driver_id": "aaa", "constructor_id": "fast", "score": 1.0}, {"driver_id": "bbb", "constructor_id": "slow", "score": 0.0}]}}
    usable = PredictionService._cache_usable

    assert usable(cached, "t", {"aaa": "fast", "bbb": None})
    assert not usable(cached, "t", {"aaa": "fast", "ccc": None})           # different driver
    assert not usable(cached, "t", {"aaa": "fast", "bbb": "fast"})         # bbb changed teams
