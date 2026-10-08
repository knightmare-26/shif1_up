"""The data keeps itself complete and correct (services/data_upkeep.py) — no scripts against
production after a change ships. OpenF1 is faked with httpx.MockTransport."""
from datetime import datetime, timezone

import httpx
import pytest

from services.data_upkeep import DataUpkeep, expected_sessions
from services.openf1_live import OpenF1Client

pytestmark = pytest.mark.asyncio
NOW = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)


def rows(n, start=1, timed=True, team="mercedes"):
    return [{"position": start + i, "driver_id": f"d{i:02d}", "constructor_id": team, "grid": None, "points": 0.0,
             "time": "0 days 00:01:30.000000" if timed else "", "fastest_lap": False, "fastest_lap_time": "",
             "status": "", "laps_completed": 10} for i in range(n)]


class FakeDb:
    def __init__(self, races, results):
        self.races, self.results, self.cache, self.drivers = races, results, {}, []

    async def get_races_by_year(self, year):
        return [r for r in self.races if r["year"] == year]

    async def get_race_results(self, race_id, session_type="race"):
        return sorted(self.results.get((race_id, session_type), []), key=lambda r: r["position"])

    async def store_race_results(self, race_id, rows_, session_type="race"):
        self.results[(race_id, session_type)] = rows_

    async def store_drivers(self, drivers, rename=False):
        self.drivers += drivers

    async def get_prediction_cache(self, circuit, session):
        return self.cache.get((circuit, session))

    async def set_prediction_cache(self, circuit, session, key, result):
        self.cache[(circuit, session)] = {"model_trained_at": key, "result": result}

    async def _run_query(self, query, params=None):
        if "GROUP BY race_id, session_type" in query:
            return [{"race_id": r, "session_type": s, "n": len(v), "top": max(x["position"] for x in v),
                     "timed": sum(1 for x in v if x["time"])} for (r, s), v in self.results.items()]
        if "_weather" in query:
            return [{"session_type": s} for (c, s) in self.cache if c == "_weather"]
        return []


def openf1(calls, sessions=("Practice 1", "Qualifying", "Sprint Qualifying")):
    def handler(request):
        name = request.url.path.rsplit("/", 1)[-1]
        calls.append(name)
        if name == "meetings":
            return httpx.Response(200, json=[{"meeting_key": 1, "meeting_name": "Chinese Grand Prix", "is_cancelled": False}])
        if name == "sessions":
            return httpx.Response(200, json=[{"session_key": i, "session_name": n, "date_end": "2025-03-22T08:00:00+00:00"}
                                             for i, n in enumerate(sessions)])
        if name == "session_result":
            return httpx.Response(200, json=[{"position": i + 1, "driver_number": 10 + i, "duration": [90 + i / 10]} for i in range(12)])
        if name == "drivers":
            return httpx.Response(200, json=[{"driver_number": 10 + i, "name_acronym": f"D{i:02d}", "team_name": "Mercedes"} for i in range(12)])
        if name == "laps":
            return httpx.Response(200, json=[{"driver_number": 10 + i, "lap_duration": 91 + i / 10} for i in range(12)])
        return httpx.Response(404, json={})
    return OpenF1Client(creds={}, per_minute=60000, transport=httpx.MockTransport(handler))


def upkeep(ingested=None, weather=None, title=None):
    async def ingest_race(db, year, rnd, session):
        ingested.append((year, rnd, session)) if ingested is not None else None
        if session == "R":
            db.results[(f"{year}_R{rnd}", "race")] = rows(20)
            return {"stored": True}
        return {"stored": False}

    async def load_weather(year, gp, code):
        (weather if weather is not None else []).append((year, gp, code))
        return {}, [{"air_temperature": 25}]

    async def rebuild(finished):
        (title if title is not None else []).append(finished)
        return True

    return DataUpkeep(ingest_race, load_weather, rebuild)


RACE = {"race_id": "2025_Chinese", "year": 2025, "round": 2, "gp": "Chinese", "date": "2025-03-23"}


def weekend(**extra):
    base = {(RACE["race_id"], s): rows(20) for s in ("race", "sprint", "fp1", "qualifying", "sprint_qualifying")}
    return {**base, **extra}


async def test_a_placeholder_position_is_renumbered_after_the_classified_drivers():
    results = weekend()
    results[(RACE["race_id"], "qualifying")] = rows(19) + [{**rows(1)[0], "driver_id": "sai", "position": 99}]
    db = FakeDb([RACE], results)
    report = await upkeep().run(db, openf1([]), {}, {}, now=NOW)

    assert report.renumbered == ["2025_Chinese qualifying"]
    assert [r["position"] for r in await db.get_race_results(RACE["race_id"], "qualifying")] == list(range(1, 21))
    assert report.needs_retrain


async def test_a_weekends_missing_sessions_come_from_openf1_and_a_sprint_weekend_has_no_fp2():
    results = weekend()
    del results[(RACE["race_id"], "qualifying")]
    results[(RACE["race_id"], "sprint_qualifying")] = rows(20, timed=False)        # stored the old way
    db = FakeDb([RACE], results)
    report = await upkeep().run(db, openf1([]), {"mercedes": "Mercedes"}, {}, now=NOW)

    assert sorted(report.sessions) == ["2025_Chinese qualifying", "2025_Chinese sprint_qualifying"]
    assert expected_sessions(2025, sprint_weekend=True) == ["fp1", "sprint_qualifying", "qualifying"]
    sq = await db.get_race_results(RACE["race_id"], "sprint_qualifying")
    assert sq[0]["driver_id"] == "d00" and sq[0]["time"] and sq[0]["constructor_id"] == "mercedes"


async def test_what_openf1_doesnt_have_isnt_asked_for_again():
    results = weekend()
    del results[(RACE["race_id"], "qualifying")]
    db, calls, job = FakeDb([RACE], results), [], upkeep()
    await job.run(db, openf1(calls, sessions=("Practice 1",)), {}, {}, now=NOW)     # no qualifying on OpenF1
    calls.clear()
    report = await job.run(db, openf1(calls, sessions=("Practice 1",)), {}, {}, now=NOW)

    assert report.sessions == [] and "session_result" not in calls and "sessions" not in calls


async def test_a_race_the_server_slept_through_is_ingested_and_a_failure_waits():
    races = [RACE, {"race_id": "2026_R5", "year": 2026, "round": 5, "gp": "Miami", "date": "2026-05-03"},
             {"race_id": "2026_R6", "year": 2026, "round": 6, "gp": "Monaco", "date": "2026-10-07"}]   # yesterday: not yet
    db, ingested = FakeDb(races, weekend()), []
    report = await upkeep(ingested=ingested).run(db, openf1([]), {}, {}, now=NOW)

    assert report.races == ["2026_R5"] and ingested[0] == (2026, 5, "R")
    assert (2026, 6, "R") not in ingested


async def test_weather_is_stored_for_sessions_without_it():
    weather = []
    report = await upkeep(weather=weather).run(FakeDb([RACE], weekend()), openf1([]), {}, {}, now=NOW)
    assert len(report.weather) == 5 and ("2025", "Chinese") == (str(weather[0][0]), weather[0][1])
    assert not report.needs_retrain                                   # weather alone doesn't retrain


async def test_the_title_track_record_is_rebuilt_only_when_a_finished_season_is_missing():
    races = [{**RACE, "year": y, "race_id": f"{y}_X"} for y in (2023, 2024, 2025)] + [{**RACE, "year": 2026, "race_id": "2026_X"}]
    db, title = FakeDb(races, {}), []
    db.cache[("_championship", "backtest")] = {"result": {"seasons": [{"year": 2024}]}}
    await upkeep(title=title).run(db, openf1([]), {}, {}, now=NOW)
    assert title == [[2023, 2024, 2025]]

    db.cache[("_championship", "backtest")] = {"result": {"seasons": [{"year": 2024}, {"year": 2025}],
                                                          "seasons_considered": [2023, 2024, 2025]}}
    title.clear()
    await upkeep(title=title).run(db, openf1([]), {}, {}, now=NOW)
    assert title == []
