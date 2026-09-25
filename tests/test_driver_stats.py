"""GET /api/driver-stats: race and sprint wins/podiums counted from the stored results.

The standings feed only has total wins (and podiums hard-coded to 0), so the Drivers tab's optional
columns come from here. Runs against the throwaway local DuckDB set up in conftest.py.
"""
import pytest
from fastapi.testclient import TestClient

import api.main as main
from api.main import app


def result(position, driver):
    return {"position": position, "driver_id": driver, "constructor_id": "team", "points": 0}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        db = main.duckdb_service
        seed = [
            (db.store_drivers, [[{"driver_id": d, "full_name": n} for d, n in
                                 [("aaa", "Ann Alpha"), ("bbb", "Ben Beta"), ("ccc", "Cal Gamma"), ("ddd", "Dee Delta")]]]),
            (db.store_races, [[
                {"race_id": "2030_One", "year": 2030, "round": 1, "gp": "One"},
                {"race_id": "2030_Two", "year": 2030, "round": 2, "gp": "Two"},
                {"race_id": "2031_One", "year": 2031, "round": 1, "gp": "One"},
            ]]),
            # 2030: aaa wins both races; bbb wins the only sprint but no race.
            (db.store_race_results, ["2030_One", [result(1, "aaa"), result(2, "bbb"), result(3, "ccc"), result(4, "ddd")]]),
            (db.store_race_results, ["2030_Two", [result(1, "aaa"), result(2, "ccc"), result(3, "ddd"), result(4, "bbb")]]),
            # (bbb also has a stale leftover row in the sprint — counted once, see below.)
            (db.store_race_results, ["2030_Two", [result(1, "bbb"), result(2, "ddd"), result(3, "aaa"), result(4, "ccc"),
                                                  result(99, "bbb")], "sprint"]),
            # Qualifying and practice rows must not count.
            (db.store_race_results, ["2030_Two", [result(1, "ddd")], "qualifying"]),
            (db.store_race_results, ["2030_Two", [result(1, "ddd")], "fp1"]),
            # 2031: no sprints.
            (db.store_race_results, ["2031_One", [result(1, "ccc"), result(2, "aaa"), result(3, "bbb")]]),
        ]
        for fn, args in seed:
            assert c.portal.call(fn, *args)
        yield c


def by_code(body):
    return {d["code"]: d for d in body["drivers"]}


def test_race_and_sprint_counts_are_kept_apart(client):
    body = client.get("/api/driver-stats?year=2030").json()
    d = by_code(body)

    assert (body["races_counted"], body["sprints_counted"]) == (2, 1)
    assert d["AAA"] == {"code": "AAA", "driver_name": "Ann Alpha",
                        "race_wins": 2, "race_podiums": 2, "sprint_wins": 0, "sprint_podiums": 1}
    # A sprint win but no race win.
    assert (d["BBB"]["race_wins"], d["BBB"]["race_podiums"], d["BBB"]["sprint_wins"], d["BBB"]["sprint_podiums"]) == (0, 1, 1, 1)
    # Pole in qualifying and topping FP1 are not wins.
    assert d["DDD"]["race_wins"] == 0 and d["DDD"]["race_podiums"] == 1 and d["DDD"]["sprint_podiums"] == 1


def test_a_season_without_sprints_counts_zero_sprint_results(client):
    body = client.get("/api/driver-stats?year=2031").json()

    assert body["sprints_counted"] == 0
    assert all(d["sprint_wins"] == 0 and d["sprint_podiums"] == 0 for d in body["drivers"])
    assert by_code(body)["CCC"]["race_wins"] == 1


def test_a_season_not_in_the_database_has_no_drivers(client):
    body = client.get("/api/driver-stats?year=1999").json()

    assert body == {"year": 1999, "races_counted": 0, "sprints_counted": 0, "drivers": []}


def test_team_counts_add_up_both_cars(client):
    """Every seeded result is for one team ("team"), so it has all the wins and every podium car."""
    body = client.get("/api/constructor-stats?year=2030").json()
    team = {t["constructor_id"]: t for t in body["constructors"]}["team"]

    assert (body["races_counted"], body["sprints_counted"]) == (2, 1)
    assert team["race_wins"] == 2                 # once per race, however many of its cars finish
    assert team["race_podiums"] == 6              # 3 cars x 2 races
    assert team["sprint_wins"] == 1 and team["sprint_podiums"] == 3   # the stale P99 row doesn't count
