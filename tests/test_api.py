"""The core read endpoints, end to end: the real app with its start-up, against the throwaway local DuckDB
and in-memory Redis set up in conftest.py. Data is stored through the app's own database service rather
than mocked, under ids no other test uses (the test database is shared by the whole run).

(This file used to test the first version of the API — a `DuckDBService` that no longer exists — so it
couldn't even be imported.)
"""
import pytest
from fastapi.testclient import TestClient

import api.main as main
from api.main import app

RACE = "2032_Testland"


def result(position, driver, team, points, status="Finished"):
    return {"position": position, "driver_id": driver, "constructor_id": team, "grid": position + 1,
            "points": points, "time": "0 days 01:31:44.742000" if position == 1 else "", "status": status,
            "laps_completed": 57}


def lap(driver, number, position):
    return {"driver_id": driver, "lap_number": number, "lap_time_ms": 93660 + number, "sector1_ms": 31000,
            "sector2_ms": 31000, "sector3_ms": 31660, "tyre": "SOFT", "pit": False, "position": position}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        db = main.duckdb_service
        seed = [
            (db.store_drivers, [[{"driver_id": "zza", "full_name": "Zed Alpha", "nationality": "Dutch", "number": 1},
                                 {"driver_id": "zzb", "full_name": "Zed Beta", "nationality": "British", "number": 4}]]),
            (db.store_races, [[{"race_id": RACE, "year": 2032, "round": 1, "gp": "Testland",
                                "date": "2032-03-07", "circuit_name": "Testland Ring", "country": "Testland"}]]),
            (db.store_race_results, [RACE, [result(1, "zza", "red_bull", 25.0),
                                            result(2, "zzb", "mclaren", 18.0, status="Retired")]]),
            (db.store_laps, [RACE, [lap("zza", 1, 1), lap("zzb", 1, 2), lap("zza", 2, 1), lap("zzb", 2, 2)]]),
        ]
        for fn, args in seed:
            assert c.portal.call(fn, *args)
        yield c


def test_health_reports_the_app_and_its_stores(client):
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "Shif1 UP API" and "timestamp" in body
    assert body["checks"]["duckdb"]["status"] == "ok"
    # The in-memory Redis stand-in is a working fallback, so at worst the app is "degraded", never down.
    assert body["status"] in ("ok", "degraded")
    assert "database" not in body["checks"]          # only reported when running against Supabase


def test_drivers_who_raced_in_a_season(client):
    body = client.get("/drivers?year=2032").json()

    assert [d["driver_id"] for d in body] == ["zza", "zzb"]
    assert body[0] == {"driver_id": "zza", "full_name": "Zed Alpha", "nationality": "Dutch", "number": 1}


def test_all_drivers(client):
    ids = {d["driver_id"] for d in client.get("/drivers").json()}
    assert {"zza", "zzb"} <= ids


def test_a_seasons_races(client):
    body = client.get("/races?year=2032").json()

    assert len(body) == 1
    assert {k: body[0][k] for k in ("race_id", "year", "round", "gp", "circuit_name")} == {
        "race_id": RACE, "year": 2032, "round": 1, "gp": "Testland", "circuit_name": "Testland Ring"}


def test_race_results_come_back_in_the_shape_the_results_table_uses(client):
    body = client.get(f"/race/{RACE}/results").json()

    assert [r["Abbreviation"] for r in body] == ["ZZA", "ZZB"]
    winner, retired = body
    assert (winner["FullName"], winner["Position"], winner["ClassifiedPosition"], winner["GridPosition"]) == \
        ("Zed Alpha", "1", "1", "2")
    assert winner["Time"] == pytest.approx(5504.742)            # 1:31:44.742
    assert winner["TeamColor"] == main.TEAM_COLORS["red_bull"] and winner["Points"] == "25.0"
    assert (retired["Status"], retired["ClassifiedPosition"]) == ("Retired", "RET")


def test_a_session_that_isnt_stored_or_available_is_a_404(client, monkeypatch):
    async def no_such_session(*args, **kwargs):
        raise ValueError("no sprint at this weekend")            # what FastF1 says for a missing session
    monkeypatch.setattr(main.ingest_service, "ingest_single_race", no_such_session)

    response = client.get(f"/race/{RACE}/results?session=S")

    assert response.status_code == 404
    assert "sprint" in response.json()["detail"]


def test_race_laps_all_drivers_and_one(client):
    every = client.get(f"/race/{RACE}/laps").json()
    assert [(l["lap_number"], l["driver_name"]) for l in every] == [
        (1, "Zed Alpha"), (1, "Zed Beta"), (2, "Zed Alpha"), (2, "Zed Beta")]

    one = client.get(f"/race/{RACE}/laps?driver=zza").json()
    assert [l["lap_number"] for l in one] == [1, 2] and {l["driver_name"] for l in one} == {"Zed Alpha"}
    assert one[0]["lap_time_ms"] == 93661 and one[0]["tyre"] == "SOFT"


def test_a_malformed_race_id_is_a_400(client):
    response = client.get("/race/Testland/laps")
    assert response.status_code == 400


def test_live_state_flat_when_there_is_some_and_a_placeholder_when_not(client):
    empty = client.get("/live/2032_Nowhere/state").json()
    assert (empty["race_id"], empty["session_status"]) == ("2032_Nowhere", "no_data")

    state = {"race_id": "2032_Testland", "session_status": "live", "current_lap": 15, "leader": "ZZA",
             "positions": [{"driver": "ZZA", "position": 1}]}
    assert client.portal.call(main.redis_service.set_live_state, "2032_Testland", state)

    body = client.get("/live/2032_Testland/state").json()
    assert (body["session_status"], body["current_lap"], body["leader"]) == ("live", 15, "ZZA")
    assert "state" not in body                                    # the Redis envelope is flattened


def test_legacy_driver_standings(client, monkeypatch):
    async def standings(year, round=None):
        return [{"position": 1, "driver_id": "zza", "driver_name": "Zed Alpha", "constructor": "Red Bull",
                 "points": 25.0, "wins": 1, "podiums": 1, "nationality": "Dutch", "number": 1, "code": "ZZA"}]
    monkeypatch.setattr(main.fastf1_service, "get_driver_standings", standings)

    response = client.get("/api/drivers?year=2024&use_cache=false")

    assert response.status_code == 200
    assert [(d["driver_id"], d["points"], d["code"]) for d in response.json()] == [("zza", 25.0, "ZZA")]
