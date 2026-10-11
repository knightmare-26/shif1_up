"""The current season's standings follow the stored results when the standings source (Jolpica) is
behind: after Singapore 2026's race it still had Antonelli on 325 (the sprint counted, the race
not) while the database had the race. The database is faked."""
from datetime import datetime

import pytest

import main
from models.f1_models import ConstructorStanding, DriverStanding

pytestmark = pytest.mark.asyncio
YEAR = datetime.now().year


def row(rnd, session, driver, team, position, points):
    return {"round": rnd, "session_type": session, "driver_id": driver, "constructor_id": team,
            "position": position, "points": points, "driver_name": driver.upper(), "constructor_name": team}


STORED = [
    row(16, "race", "ant", "mercedes", 1, 25), row(16, "race", "rus", "mercedes", 2, 18), row(16, "race", "ver", "red_bull", 3, 15),
    row(17, "sprint", "ver", "red_bull", 1, 8), row(17, "sprint", "rus", "mercedes", 2, 7), row(17, "sprint", "ant", "mercedes", 4, 5),
    row(17, "race", "ver", "red_bull", 1, 25), row(17, "race", "rus", "mercedes", 2, 18), row(17, "race", "ant", "mercedes", 3, 15),
]


class Db:
    def __init__(self, rows):
        self.rows = rows

    async def get_season_results(self, year):
        return self.rows


def drivers(*points):
    """The source's table, as Jolpica serves it (round 17, sprint counted, race not)."""
    names = [("ant", "Andrea Kimi Antonelli", "Mercedes", 12), ("rus", "George Russell", "Mercedes", 63),
             ("ver", "Max Verstappen", "Red Bull", 3)]
    return [DriverStanding(position=i, driver_id=d, driver_name=n, constructor=c, points=p, wins=1 if i == 1 else 0,
                           nationality="X", number=num, code=d.upper())
            for i, ((d, n, c, num), p) in enumerate(zip(names, points), start=1)]


async def test_a_round_the_source_hasnt_added_comes_from_the_stored_results(monkeypatch):
    monkeypatch.setattr(main, "duckdb_service", Db(STORED))
    out = await main._with_stored_results(drivers(30, 25, 23), YEAR, "driver_id")

    by_code = {r["code"]: r for r in out}
    assert (by_code["VER"]["points"], by_code["RUS"]["points"], by_code["ANT"]["points"]) == (48.0, 43.0, 45.0)
    assert [r["code"] for r in out] == ["VER", "ANT", "RUS"]                       # re-ordered, positions 1-3
    assert [r["position"] for r in out] == [1, 2, 3]
    assert by_code["VER"]["wins"] == 1 and by_code["ANT"]["wins"] == 1             # Grand Prix wins
    assert by_code["ANT"]["driver_name"] == "Andrea Kimi Antonelli" and by_code["ANT"]["number"] == 12   # the source's


async def test_the_source_is_used_as_is_once_it_has_caught_up_or_for_another_season(monkeypatch):
    monkeypatch.setattr(main, "duckdb_service", Db(STORED))
    caught_up = drivers(45, 43, 48)
    assert await main._with_stored_results(caught_up, YEAR, "driver_id") is caught_up
    behind = drivers(30, 25, 23)
    assert await main._with_stored_results(behind, YEAR - 1, "driver_id") is behind


async def test_constructors_too(monkeypatch):
    monkeypatch.setattr(main, "duckdb_service", Db(STORED))
    source = [ConstructorStanding(position=1, constructor_id="mercedes", constructor_name="Mercedes", points=55, wins=1, nationality="X"),
              ConstructorStanding(position=2, constructor_id="red_bull", constructor_name="Red Bull", points=23, wins=0, nationality="X")]
    out = await main._with_stored_results(source, YEAR, "constructor_id")
    assert [(r["constructor_id"], r["points"], r["wins"]) for r in out] == [("mercedes", 88.0, 1), ("red_bull", 48.0, 1)]


async def test_a_database_problem_leaves_the_source_alone(monkeypatch):
    class Broken:
        async def get_season_results(self, year):
            raise RuntimeError("database waking")
    monkeypatch.setattr(main, "duckdb_service", Broken())
    source = drivers(30, 25, 23)
    assert await main._with_stored_results(source, YEAR, "driver_id") is source
