#!/usr/bin/env python3
"""
Generate static JSON data files from the Jolpica API (free, no API key).
Output goes to public/data/ — commit these files so the frontend
can serve them from Vercel's CDN without any backend calls.

Usage:
    python scripts/generate_static_data.py
    python scripts/generate_static_data.py --results-from 2018   # race results from a year
    python scripts/generate_static_data.py --year 2024           # refresh one year only
    python scripts/generate_static_data.py --stats-only --standings-from 2000   # result counts only

Result counts (public/data/stats): the Drivers/Teams tabs' optional columns — race and sprint
wins/podiums, poles, top-3 starts. The API counts them from its database, which holds 2022 on;
earlier seasons are counted here, the same way, from Jolpica's results.

Only finished seasons are written (see the note at the bottom).
"""

import argparse
import asyncio
import json
import logging
from pathlib import Path

import aiohttp

BASE_URL    = "https://api.jolpi.ca/ergast/f1"
OUT_DIR     = Path(__file__).parent.parent / "public" / "data"
FIRST_WCC   = 1958   # constructors championship started
STORED_FROM = 2022   # the API counts result stats from its own database from this season on
COUNTS      = ("race_wins", "race_podiums", "sprint_wins", "sprint_podiums", "poles", "top3_starts")
LOG_LEVEL   = logging.INFO

# Polite rate-limiting: wait this long between every API call
DELAY_BETWEEN_CALLS  = 2.0   # seconds
DELAY_BETWEEN_YEARS  = 3.0   # seconds
MAX_RETRIES          = 5
RETRY_BACKOFF        = 10.0  # seconds to wait on 429

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

async def get_json(session: aiohttp.ClientSession, url: str) -> dict:
    for attempt in range(1, MAX_RETRIES + 1):
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as r:
            if r.status == 429:
                wait = RETRY_BACKOFF * attempt
                log.warning("Rate-limited, waiting %.0fs (attempt %d/%d)…", wait, attempt, MAX_RETRIES)
                await asyncio.sleep(wait)
                continue
            r.raise_for_status()
            await asyncio.sleep(DELAY_BETWEEN_CALLS)   # polite gap after every success
            return await r.json()
    raise RuntimeError(f"Max retries exceeded for {url}")


# ---------------------------------------------------------------------------
# Fetchers
# ---------------------------------------------------------------------------

async def fetch_driver_standings(session, year: int) -> list:
    url  = f"{BASE_URL}/{year}/driverStandings.json?limit=50"
    data = await get_json(session, url)
    lists = data.get("MRData", {}).get("StandingsTable", {}).get("StandingsLists", [])
    if not lists:
        return []
    drivers = []
    for d in lists[0].get("DriverStandings", []):
        info = d.get("Driver", {})
        team = (d.get("Constructors") or [{}])[0]
        drivers.append({
            "position":     int(d.get("position", 0)),
            "driver_id":    info.get("driverId", ""),
            "driver_name":  f"{info.get('givenName','')} {info.get('familyName','')}".strip(),
            "nationality":  info.get("nationality", ""),
            "number":       info.get("permanentNumber", ""),
            "constructor":  team.get("name", ""),
            "points":       float(d.get("points", 0)),
            "wins":         int(d.get("wins", 0)),
        })
    return drivers


async def fetch_constructor_standings(session, year: int) -> list:
    url  = f"{BASE_URL}/{year}/constructorStandings.json?limit=30"
    data = await get_json(session, url)
    lists = data.get("MRData", {}).get("StandingsTable", {}).get("StandingsLists", [])
    if not lists:
        return []
    constructors = []
    for c in lists[0].get("ConstructorStandings", []):
        info = c.get("Constructor", {})
        constructors.append({
            "position":          int(c.get("position", 0)),
            "constructor_id":    info.get("constructorId", ""),
            "constructor_name":  info.get("name", ""),
            "nationality":       info.get("nationality", ""),
            "points":            float(c.get("points", 0)),
            "wins":              int(c.get("wins", 0)),
        })
    return constructors


async def fetch_schedule(session, year: int) -> list:
    url  = f"{BASE_URL}/{year}.json?limit=30"
    data = await get_json(session, url)
    races_raw = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
    races = []
    for r in races_raw:
        circuit  = r.get("Circuit", {})
        location = circuit.get("Location", {})
        races.append({
            "round":         int(r.get("round", 0)),
            "race_name":     r.get("raceName", ""),
            "circuit_name":  circuit.get("circuitName", ""),
            "country":       location.get("country", ""),
            "location":      location.get("locality", ""),
            "date":          r.get("date", ""),
            "time":          r.get("time", ""),
            # Jolpica lists a weekend's sessions; a sprint weekend has a "Sprint" one (2021 on).
            "is_sprint":     "Sprint" in r,
        })
    return races


async def fetch_race_results(session, year: int, round_num: int) -> list:
    url  = f"{BASE_URL}/{year}/{round_num}/results.json?limit=30"
    data = await get_json(session, url)
    races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
    if not races:
        return []
    results = []
    for r in races[0].get("Results", []):
        driver      = r.get("Driver", {})
        constructor = r.get("Constructor", {})
        fastest     = r.get("FastestLap", {})
        results.append({
            "position":         int(r.get("position", 99)),
            "driver_id":        driver.get("driverId", ""),
            "driver_name":      f"{driver.get('givenName','')} {driver.get('familyName','')}".strip(),
            "constructor_id":   constructor.get("constructorId", ""),
            "constructor_name": constructor.get("name", ""),
            "points":           float(r.get("points", 0)),
            "grid":             int(r.get("grid", 0)),
            "laps":             int(r.get("laps", 0)),
            "status":           r.get("status", ""),
            "time":             r.get("Time", {}).get("time", ""),
            "fastest_lap":      fastest.get("rank") == "1",
            "fastest_lap_time": fastest.get("Time", {}).get("time", ""),
        })
    return results


async def fetch_season(session, year: int, what: str, table: str) -> list:
    """A whole season of one Jolpica results table (results, qualifying, sprint), one entry per
    round. Pages hold 100 rows and can split a race between them, so pages are merged by round."""
    races: dict[int, dict] = {}
    offset, total = 0, 1
    while offset < total:
        data = (await get_json(session, f"{BASE_URL}/{year}/{what}.json?limit=100&offset={offset}"))["MRData"]
        total = int(data.get("total", 0))
        page = data.get("RaceTable", {}).get("Races", [])
        if not page:
            break
        for race in page:
            entry = races.setdefault(int(race["round"]), {"round": int(race["round"]), table: []})
            entry[table].extend(race.get(table, []))
        offset += int(data.get("limit", 100))
    return [races[r] for r in sorted(races)]


def season_stats(year: int, races: list, qualifying: list, sprints: list) -> tuple[dict, dict]:
    """The Drivers/Teams tabs' result counts for a season, defined as the API's
    (GET /api/driver-stats, /api/constructor-stats): wins and podiums in the race and the sprint,
    poles (P1 in qualifying) and top-3 starts (a Grand Prix started from grid slots 1-3; a pit-lane
    start, grid 0, doesn't count). Jolpica has qualifying for every race from 2003 but only a few
    before, so a race without it takes the pole from the grid: the driver who started first
    (`poles_from_grid` lists those rounds). Teams count wins and poles once per race, podiums and
    top-3 starts per car."""
    drivers: dict[str, dict] = {}
    teams: dict[str, dict] = {}

    def rows(result):
        d, c = result["Driver"], result["Constructor"]
        driver = drivers.setdefault(d["driverId"], {
            "code": d.get("code", ""), "driver_id": d["driverId"],
            "driver_name": f"{d.get('givenName', '')} {d.get('familyName', '')}".strip(),
            **{k: 0 for k in COUNTS}})
        team = teams.setdefault(c["constructorId"], {
            "constructor_id": c["constructorId"], "constructor_name": c.get("name", ""), **{k: 0 for k in COUNTS}})
        return driver, team

    def add(result, key):
        for row in rows(result):
            row[key] += 1

    pole_sitters = {q["round"]: next((r for r in q["QualifyingResults"] if r.get("position") == "1"), None)
                    for q in qualifying}
    poles_from_grid = []
    for race in races:
        for r in race["Results"]:
            rows(r)                                   # everyone who raced gets a row, zeros included
            position, grid = int(r["position"]), int(r.get("grid") or 0)
            if position == 1:
                add(r, "race_wins")
            if position <= 3:
                add(r, "race_podiums")
            if 1 <= grid <= 3:
                add(r, "top3_starts")
        pole = pole_sitters.get(race["round"])
        if pole is None:
            pole = next((r for r in race["Results"] if int(r.get("grid") or 0) == 1), None)
            if pole is not None:
                poles_from_grid.append(race["round"])
        if pole is not None:
            add(pole, "poles")
    for sprint in sprints:
        for r in sprint["SprintResults"]:
            position = int(r["position"])
            if position == 1:
                add(r, "sprint_wins")
            if position <= 3:
                add(r, "sprint_podiums")

    order = lambda row: tuple(-row[k] for k in COUNTS)  # noqa: E731 - as the API sorts
    covered = {"year": year, "races_counted": len(races), "sprints_counted": len(sprints),
               "poles_from_grid": poles_from_grid}
    return ({**covered, "drivers": sorted(drivers.values(), key=order)},
            {**covered, "constructors": sorted(teams.values(), key=order)})


async def fetch_season_stats(session, year: int) -> tuple[dict, dict]:
    races = await fetch_season(session, year, "results", "Results")
    qualifying = await fetch_season(session, year, "qualifying", "QualifyingResults")
    sprints = await fetch_season(session, year, "sprint", "SprintResults") if year >= 2021 else []
    return season_stats(year, races, qualifying, sprints)


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------

def write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def write_stats(session, year: int, refresh: bool) -> None:
    """The result counts for a season the API doesn't hold (before STORED_FROM). A finished season
    doesn't change, so an existing file is kept unless this year was asked for by name."""
    paths = (OUT_DIR / "stats" / f"{year}_drivers.json", OUT_DIR / "stats" / f"{year}_constructors.json")
    if year >= STORED_FROM or (all(p.exists() for p in paths) and not refresh):
        return
    try:
        drivers, constructors = await fetch_season_stats(session, year)
    except Exception as e:
        log.warning("  result counts failed: %s", e)
        return
    if drivers["races_counted"]:
        write(paths[0], drivers)
        write(paths[1], constructors)
        log.info("  result counts: %d races, %d sprints, poles from the grid in %d",
                 drivers["races_counted"], drivers["sprints_counted"], len(drivers["poles_from_grid"]))


async def run(years: list[int], results_from: int, stats_only: bool = False, refresh: bool = False):
    connector = aiohttp.TCPConnector(limit=5)   # polite concurrency
    async with aiohttp.ClientSession(connector=connector) as session:

        for year in years:
            log.info("Year %d …", year)
            await write_stats(session, year, refresh)
            if stats_only:
                continue

            # Driver standings
            try:
                drivers = await fetch_driver_standings(session, year)
                if drivers:
                    write(OUT_DIR / "standings" / f"{year}_drivers.json", drivers)
                    log.info("  drivers: %d", len(drivers))
            except Exception as e:
                log.warning("  driver standings failed: %s", e)

            # Constructor standings (WCC started 1958)
            if year >= FIRST_WCC:
                try:
                    constructors = await fetch_constructor_standings(session, year)
                    if constructors:
                        write(OUT_DIR / "standings" / f"{year}_constructors.json", constructors)
                        log.info("  constructors: %d", len(constructors))
                except Exception as e:
                    log.warning("  constructor standings failed: %s", e)

            # Race schedule
            try:
                schedule = await fetch_schedule(session, year)
                if schedule:
                    write(OUT_DIR / "schedule" / f"{year}.json", schedule)
                    log.info("  schedule: %d races", len(schedule))
            except Exception as e:
                log.warning("  schedule failed: %s", e)

            # Race results (only for years >= results_from)
            if year >= results_from:
                schedule_path = OUT_DIR / "schedule" / f"{year}.json"
                if schedule_path.exists():
                    races = json.loads(schedule_path.read_text())
                    for race in races:
                        rnd      = race["round"]
                        gp_slug  = race["race_name"].replace(" ", "_").replace("/", "-")
                        out_path = OUT_DIR / "results" / f"{year}_{rnd:02d}_{gp_slug}.json"
                        if out_path.exists():
                            continue   # already fetched
                        try:
                            results = await fetch_race_results(session, year, rnd)
                            if results:
                                write(out_path, {"race": race, "results": results})
                        except Exception as e:
                            log.warning("  result %d R%d failed: %s", year, rnd, e)
                        # (DELAY_BETWEEN_CALLS already applied inside get_json)

            await asyncio.sleep(DELAY_BETWEEN_YEARS)

    log.info("Done. Files written to %s", OUT_DIR)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-from", type=int, default=2018,
                        help="Fetch per-race results starting from this year (default: 2018)")
    parser.add_argument("--year", type=int, default=None,
                        help="Refresh a single year only")
    parser.add_argument("--standings-from", type=int, default=1950,
                        help="Fetch standings/schedule from this year (default: 1950)")
    parser.add_argument("--stats-only", action="store_true",
                        help=f"Only the result counts (public/data/stats; seasons before {STORED_FROM})")
    args = parser.parse_args()

    import datetime
    current_year = datetime.datetime.now().year
    # Finished seasons only: the frontend ignores snapshots of the current season (it changes every
    # race weekend), and one left in the repo would be served — stale — once that season is over.
    # Run this again after the final race to add the season just finished.
    if args.year and args.year >= current_year:
        parser.error(f"{args.year} isn't finished; snapshots are only for past seasons")
    years = [args.year] if args.year else list(range(args.standings_from, current_year))
    if args.stats_only:
        years = [y for y in years if y < STORED_FROM]

    asyncio.run(run(years, results_from=args.results_from, stats_only=args.stats_only, refresh=bool(args.year)))
