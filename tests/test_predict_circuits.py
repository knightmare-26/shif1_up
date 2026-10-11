"""Once a session of the coming weekend is finished it leaves the Predictions page for Predicted vs
Actual: /predict/circuits lists the weekend's finished sessions, and drops the weekend once its race
is stored."""
from datetime import datetime, timedelta

import pytest

import main
from models.f1_models import RaceEvent

pytestmark = pytest.mark.asyncio


def event(rnd, days_ahead, sprint=False, sessions=None):
    day = (datetime.utcnow().date() + timedelta(days=days_ahead)).isoformat()
    return RaceEvent(round=rnd, race_name=f"GP {rnd}", circuit_name=f"Circuit {rnd}", country="X", location="X",
                     date=day, time="13:00:00Z", is_sprint=sprint, sessions=sessions)


def started(hours_ago):
    """A session start `hours_ago` hours before now, as FastF1's schedule gives it (UTC)."""
    return (datetime.utcnow() - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


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
    assert [c["finished_sessions"] for c in out] == [[], []]


async def test_a_session_over_by_the_clock_leaves_before_its_result_is_stored(circuits):
    """Saturday afternoon: sprint qualifying stored, the sprint ended an hour ago (its result not in
    yet), qualifying still to come."""
    sessions = {"Practice 1": started(30), "Sprint Qualifying": started(26), "Sprint": started(2),
                "Qualifying": started(-2), "Race": started(-25)}
    out = await circuits({"r18": {"sprint_qualifying"}}, [event(18, 1, sprint=True, sessions=sessions)])

    assert (out[0]["completed_sessions"], out[0]["finished_sessions"]) == (["sprint_qualifying"], ["sprint"])


async def test_sprint_qualifying_is_over_once_the_sprint_is_stored(circuits):
    """Jolpica (the fallback while OpenF1 is shut) has the sprint but no sprint qualifying: it must
    still leave the page. Without session times the weekend's order says so."""
    out = await circuits({"r18": {"sprint"}}, [event(18, 1, sprint=True)])
    assert (out[0]["completed_sessions"], out[0]["finished_sessions"]) == (["sprint"], ["sprint_qualifying"])


async def test_once_the_race_is_over_the_next_weekend_is_upcoming(circuits):
    sessions = {"Qualifying": started(27), "Race": started(3)}
    out = await circuits({"r18": {"qualifying"}}, [event(18, 0, sessions=sessions), event(19, 7)])
    assert [c["round"] for c in out] == [19]


async def test_a_session_still_running_stays(circuits):
    sessions = {"Qualifying": started(0.5), "Race": started(-23)}
    out = await circuits({}, [event(18, 1, sessions=sessions)])
    assert out[0]["finished_sessions"] == []


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
