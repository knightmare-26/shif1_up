"""scripts/generate_static_data.py --stats-only: the Drivers/Teams tabs' result counts for seasons
before the API's database (2022), counted from Jolpica's results the same way the API counts them."""
import asyncio
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "generate_static_data", Path(__file__).parent.parent / "scripts" / "generate_static_data.py")
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)


def result(driver, team, position, grid=None, code=None):
    row = {"position": str(position),
           "Driver": {"driverId": driver, "givenName": driver.title(), "familyName": "", **({"code": code} if code else {})},
           "Constructor": {"constructorId": team, "name": team.title()}}
    if grid is not None:
        row["grid"] = str(grid)
    return row


def counts(rows, key, ident):
    return {k: v for k, v in next(r for r in rows if r[key] == ident).items() if k in gen.COUNTS}


# Monza 2005: Raikkonen fastest in qualifying, a 10-place engine penalty, Montoya started first.
MONZA = {"round": 15, "Results": [
    result("montoya", "mclaren", 1, grid=1), result("alonso", "renault", 2, grid=2),
    result("fisichella", "renault", 3, grid=8), result("raikkonen", "mclaren", 4, grid=11),
    result("trulli", "toyota", 5, grid=0),      # from the pit lane: not a top-3 start
]}
MONZA_QUALI = {"round": 15, "QualifyingResults": [
    result("raikkonen", "mclaren", 1), result("montoya", "mclaren", 2), result("alonso", "renault", 3)]}
# A 2000-era race Jolpica has no qualifying for: the pole is whoever started first.
OLD = {"round": 3, "Results": [result("alonso", "renault", 1, grid=2), result("montoya", "mclaren", 2, grid=1)]}
SPRINT = {"round": 15, "SprintResults": [result("alonso", "renault", 1), result("raikkonen", "mclaren", 2)]}


def test_counts_like_the_api_pole_from_qualifying_or_else_the_grid():
    drivers, teams = gen.season_stats(2005, [MONZA, OLD], [MONZA_QUALI], [SPRINT])

    assert drivers["races_counted"] == 2 and drivers["sprints_counted"] == 1
    assert drivers["poles_from_grid"] == [3]
    rows = drivers["drivers"]
    # Pole = P1 in qualifying (as the API counts 2022 on), so Monza's is Raikkonen's despite the penalty.
    assert counts(rows, "driver_id", "raikkonen") == {
        "race_wins": 0, "race_podiums": 0, "sprint_wins": 0, "sprint_podiums": 1, "poles": 1, "top3_starts": 0}
    assert counts(rows, "driver_id", "montoya") == {
        "race_wins": 1, "race_podiums": 2, "sprint_wins": 0, "sprint_podiums": 0, "poles": 1, "top3_starts": 2}
    assert counts(rows, "driver_id", "alonso") == {
        "race_wins": 1, "race_podiums": 2, "sprint_wins": 1, "sprint_podiums": 1, "poles": 0, "top3_starts": 2}
    assert counts(rows, "driver_id", "trulli")["top3_starts"] == 0       # everyone who raced has a row
    assert rows[0]["driver_id"] in ("alonso", "montoya")                  # sorted as the API sorts

    # Teams: podiums and top-3 starts per car, wins and poles once per race.
    assert counts(teams["constructors"], "constructor_id", "renault") == {
        "race_wins": 1, "race_podiums": 3, "sprint_wins": 1, "sprint_podiums": 1, "poles": 0, "top3_starts": 2}
    assert counts(teams["constructors"], "constructor_id", "mclaren") == {
        "race_wins": 1, "race_podiums": 2, "sprint_wins": 0, "sprint_podiums": 1, "poles": 2, "top3_starts": 2}


def test_driver_rows_carry_the_code_when_jolpica_has_one():
    race = {"round": 1, "Results": [result("hamilton", "mclaren", 1, grid=1, code="HAM"), result("barrichello", "honda", 2, grid=3)]}
    rows = gen.season_stats(2007, [race], [], [])[0]["drivers"]

    assert next(r for r in rows if r["driver_id"] == "hamilton")["code"] == "HAM"
    assert next(r for r in rows if r["driver_id"] == "barrichello")["code"] == ""


def test_a_race_split_across_pages_is_merged(monkeypatch):
    pages = {
        0: {"total": "3", "limit": "2", "RaceTable": {"Races": [
            {"round": "1", "Results": [result("a", "x", 1, grid=1), result("b", "x", 2, grid=2)]}]}},
        2: {"total": "3", "limit": "2", "RaceTable": {"Races": [
            {"round": "1", "Results": [result("c", "y", 3, grid=3)]}]}},
    }

    async def fake_get_json(session, url):
        return {"MRData": pages[int(url.rsplit("offset=", 1)[1])]}

    monkeypatch.setattr(gen, "get_json", fake_get_json)
    races = asyncio.run(gen.fetch_season(None, 2001, "results", "Results"))

    assert [r["round"] for r in races] == [1]
    assert [r["Driver"]["driverId"] for r in races[0]["Results"]] == ["a", "b", "c"]


def test_seasons_in_the_database_are_left_to_the_api(tmp_path, monkeypatch):
    monkeypatch.setattr(gen, "OUT_DIR", tmp_path)

    async def boom(*_):
        raise AssertionError("fetched a season the API counts itself")

    monkeypatch.setattr(gen, "fetch_season_stats", boom)
    asyncio.run(gen.write_stats(None, gen.STORED_FROM, refresh=True))

    assert not (tmp_path / "stats").exists()
