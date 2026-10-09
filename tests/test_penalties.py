"""Penalties from the stewards' race-control messages (services/penalties.py), and the endpoint the
Race Results page reads them from. OpenF1 is faked; the stored results are the throwaway database."""
import pytest
from fastapi.testclient import TestClient

import api.main as main
from api.main import app
from services.openf1_live import OpenF1Locked
from services.penalties import grid_changes, parse, relevant

MESSAGES = [
    {"lap_number": 12, "message": "FIA STEWARDS: 5 SECOND TIME PENALTY FOR CAR 44 (HAM) - SPEEDING IN THE PIT LANE (15:39:17)"},
    {"lap_number": 30, "message": "FIA STEWARDS: 10 SECOND TIME PENALTY FOR CAR 44 (HAM) - CAUSING A COLLISION"},
    {"lap_number": 1, "message": "FIA STEWARDS: STOP-AND-GO PENALTY FOR CAR 43 (COL) - STARTING PROCEDURE INFRINGEMENT"},
    {"lap_number": 4, "message": "FIA STEWARDS: PENALTY SERVED - STOP-AND-GO PENALTY FOR CAR 43 (COL) - STARTING PROCEDURE INFRINGEMENT"},
    {"lap_number": 5, "message": "FIA STEWARDS: DRIVE THROUGH PENALTY FOR CAR 41 (LIN) - YELLOW FLAG INFRINGEMENT (15:04:49)"},
    {"lap_number": 7, "message": "FIA STEWARDS: WARNING FOR CAR 55 (SAI) - MOVING UNDER BRAKING (16:19:05)"},
    {"lap_number": 9, "message": "BLACK AND WHITE FLAG FOR CAR 27 (HUL) - TRACK LIMITS"},
    {"lap_number": 5, "message": "CAR 27 (HUL) TIME 1:23.646 DELETED - TRACK LIMITS AT TURN 3 LAP 5 15:40:03"},
    {"lap_number": 2, "message": "FIA STEWARDS: 5 SECOND TIME PENALTY FOR CAR 5 (BOR) - VSC INFRINGEMENT"},
    {"lap_number": None, "message": "FIA STEWARDS: CAR 16 (LEC) DISQUALIFIED - PLANK WEAR"},
    {"lap_number": 3, "message": "FIA STEWARDS: INCIDENT INVOLVING CAR 23 (ALB) REVIEWED NO FURTHER INVESTIGATION - FAILING TO FOLLOW"},
    {"lap_number": 3, "message": "YELLOW IN TRACK SECTOR 5"},
]


def test_only_the_stewards_messages_flags_and_deleted_laps_are_kept():
    kept = relevant(MESSAGES)
    assert len(kept) == len(MESSAGES) - 1 and all("YELLOW IN TRACK" not in m["message"] for m in kept)


def test_each_decision_is_read_with_its_reason():
    decisions = {(d["driver"], d["kind"], d["seconds"]): d for d in parse(relevant(MESSAGES))["decisions"]}

    assert decisions[("HAM", "time", 5)]["reason"] == "Speeding in the pit lane"   # the clock is dropped
    assert decisions[("LIN", "drive_through", None)]["lap"] == 5
    assert decisions[("BOR", "time", 5)]["reason"] == "VSC infringement"
    assert decisions[("LEC", "disqualified", None)]["reason"] == "Plank wear"
    assert ("SAI", "warning", None) in decisions and ("HUL", "black_and_white", None) in decisions
    assert not any(d[0] == "ALB" for d in decisions)                               # reviewed, no action


def test_a_served_penalty_is_marked_not_counted_twice():
    stop_go = [d for d in parse(MESSAGES)["decisions"] if d["driver"] == "COL"]
    assert len(stop_go) == 1 and stop_go[0]["served"]


def test_the_summary_per_driver_adds_up_time_penalties_and_counts_deleted_laps():
    drivers = parse(MESSAGES)["drivers"]

    assert drivers["HAM"]["time_penalty_seconds"] == 15 and drivers["HAM"]["penalties"] == ["time", "time"]
    assert drivers["HUL"]["black_and_white"] and drivers["HUL"]["deleted_laps"] == 1 and drivers["HUL"]["penalties"] == []
    assert drivers["LEC"]["disqualified"]
    assert drivers["SAI"]["warnings"] == 1 and drivers["SAI"]["penalties"] == []   # a warning isn't a penalty
    assert parse(MESSAGES)["deleted_laps"] == [
        {"driver": "HUL", "number": 27, "time": "1:23.646", "lap": 5, "reason": "Track limits at turn 3"}]


def test_grid_changes_list_drivers_who_started_behind_where_they_qualified():
    race = [{"driver_id": "had", "grid": 8}, {"driver_id": "ver", "grid": 1}, {"driver_id": "ant", "grid": 3},
            {"driver_id": "col", "grid": 0}, {"driver_id": "new", "grid": 5}]
    quali = [{"driver_id": d, "position": p} for d, p in (("ver", 1), ("ham", 2), ("had", 3), ("ant", 4), ("col", 99))]

    # ANT moved up when HAD dropped back (not listed); COL's P99 is ranked within the session (P5)
    assert grid_changes(race, quali) == {
        "HAD": {"qualified": 3, "started": 8, "pit_lane": False},
        "COL": {"qualified": 5, "started": None, "pit_lane": True},
    }


# --- the endpoint ------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        db = main.duckdb_service
        quali = [{"position": i, "driver_id": d, "constructor_id": "t", "points": 0}
                 for i, d in enumerate(("ver", "ham", "had"), start=1)]
        race = [{"position": i, "driver_id": d, "constructor_id": "t", "points": 0, "grid": g}
                for i, (d, g) in enumerate((("ver", 1), ("ham", 2), ("had", 8)), start=1)]
        seed = [
            (db.store_races, [[{"race_id": "2035_Testland", "year": 2035, "round": 1, "gp": "Testland"}]]),
            (db.store_race_results, ["2035_Testland", quali, "qualifying"]),
            (db.store_race_results, ["2035_Testland", race]),
        ]
        for fn, args in seed:
            assert c.portal.call(fn, *args)
        yield c


def test_a_races_penalties_and_grid_changes(client, monkeypatch):
    async def load(year, gp, code):
        return relevant(MESSAGES)
    monkeypatch.setattr(main.session_replays, "load_penalties", load)

    body = client.get("/api/sessions/2035/R/penalties?gp=Testland Grand Prix").json()

    assert body["stewards"] == "ok"
    assert body["drivers"]["HAM"]["time_penalty_seconds"] == 15
    assert body["grid"] == {"HAD": {"qualified": 3, "started": 8, "pit_lane": False}}


def test_while_openf1_is_locked_the_grid_changes_still_show(client, monkeypatch):
    async def locked(year, gp, code):
        raise OpenF1Locked("Live F1 session in progress")
    monkeypatch.setattr(main.session_replays, "load_penalties", locked)

    body = client.get("/api/sessions/2035/R/penalties?gp=Testland").json()

    assert body["stewards"] == "locked" and body["decisions"] == []
    assert "HAD" in body["grid"]


def test_qualifying_has_no_grid_changes_and_an_unknown_session_is_refused(client, monkeypatch):
    async def load(year, gp, code):
        return []
    monkeypatch.setattr(main.session_replays, "load_penalties", load)

    assert client.get("/api/sessions/2035/Q/penalties?gp=Testland").json()["grid"] == {}
    assert client.get("/api/sessions/2035/XX/penalties?gp=Testland").status_code == 422


def test_every_way_a_lap_time_is_deleted_and_a_reinstated_one_no_longer_counts():
    out = parse([
        {"lap_number": 3, "message": "CAR 55 (SAI) TIME 1:25.773 DELETED - TRACK LIMITS AT TURN 3 LAP 3 16:02:37"},
        {"lap_number": 7, "message": "CAR 44 (HAM) LAP DELETED - TRACK LIMITS AT TURN 1 LAP 7 16:08:57 (PIT)"},
        {"lap_number": None, "message": "CAR LEC TIME 1:36.518 DELETED - TRACK LIMITS AT TURN 14 (NEXT LAP) (Q1)"},
        {"lap_number": None, "message": "CAR LAW TIME DELETED - TRACK LIMITS AT TURN 14 (NEXT LAP PIT) (Q2)"},
        {"lap_number": 9, "message": "CAR 11 (PER) TIME 1:31.451 DELETED - TRACK LIMITS AT TURN 3 LAP 9 14:10:00"},
        {"lap_number": 12, "message": "CAR 11 (PER) TIME 1:31.451 WILL BE REINSTATED"},
        {"lap_number": 1, "message": "CAR 55 (SAI) LAP 3 WILL BE REINSTATED"},
    ])

    assert [(d["driver"], d["time"], d["lap"]) for d in out["deleted_laps"]] == [
        ("HAM", None, 7), ("LEC", "1:36.518", None), ("LAW", None, None)]
    assert out["deleted_laps"][1]["reason"] == "Track limits at turn 14"
    assert "SAI" not in out["drivers"] and "PER" not in out["drivers"]     # reinstated: nothing left to show
    assert len(relevant([{"message": "CAR 11 (PER) TIME 1:31.451 WILL BE REINSTATED"}])) == 1
