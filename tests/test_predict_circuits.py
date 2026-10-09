"""Once a session of the coming weekend is finished it leaves the Predictions page for Predicted vs
Actual: /predict/circuits lists the weekend's finished sessions, and drops the weekend once its race
is stored."""
from datetime import datetime, timedelta

import pytest

import main
from models.f1_models import RaceEvent

pytestmark = pytest.mark.asyncio


def event(rnd, days_ahead, sprint=False):
    day = (datetime.utcnow().date() + timedelta(days=days_ahead)).isoformat()
    return RaceEvent(round=rnd, race_name=f"GP {rnd}", circuit_name=f"Circuit {rnd}", country="X", location="X",
                     date=day, time="13:00:00Z", is_sprint=sprint)


class Db:
    def __init__(self, stored):
        self.stored = stored          # race_id -> session types with results

    async def get_races_by_year(self, year):
        return [{"race_id": f"r{n}", "round": n} for n in (17, 18, 19)]

    async def get_race_results(self, race_id, session_type="race"):
        return [{"driver_id": "ver"}] if session_type in self.stored.get(race_id, ()) else []


@pytest.fixture
def circuits(monkeypatch):
    async def setup(stored, schedule):
        class Schedule:
            async def get_race_schedule(self, year):
                return schedule
        monkeypatch.setattr(main, "duckdb_service", Db(stored))
        monkeypatch.setattr(main.prediction_service, "_trained", True)
        monkeypatch.setattr(main, "fastf1_service", Schedule())
        return await main.predict_circuits()
    return setup


async def test_a_weekend_under_way_lists_its_finished_sessions(circuits):
    out = await circuits({"r18": {"fp1", "sprint_qualifying", "sprint", "qualifying"}}, [event(18, 1, sprint=True), event(19, 8)])

    assert [(c["round"], c["completed_sessions"]) for c in out] == [
        (18, ["sprint_qualifying", "sprint", "qualifying"]), (19, [])]


async def test_the_weekend_drops_out_once_its_race_is_stored(circuits):
    out = await circuits({"r18": {"qualifying", "race"}}, [event(18, 0), event(19, 7)])

    assert [c["round"] for c in out] == [19]


async def test_only_this_weekend_is_checked_and_a_missing_database_hides_nothing(circuits, monkeypatch):
    out = await circuits({"r19": {"qualifying"}}, [event(18, 2), event(19, 9)])
    assert [c["completed_sessions"] for c in out] == [[], []]       # round 19 is a week away

    monkeypatch.setattr(main, "duckdb_service", None)
    assert await main._completed_sessions(2026, [18]) == {}


async def test_a_prediction_is_made_for_the_coming_races_place_on_the_calendar(monkeypatch):
    """The round is a model input: the race's own, not the one the circuit usually is."""
    class Schedule:
        async def get_race_schedule(self, year):
            return [event(5, -150), event(17, 3), event(18, 17)]
    monkeypatch.setattr(main, "fastf1_service", Schedule())

    assert await main._calendar_round("Circuit 17") == 17
    assert await main._calendar_round("Circuit 5") == 5          # already run this season: its round
    assert await main._calendar_round("Nowhere") is None
