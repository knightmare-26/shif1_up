#!/usr/bin/env python3
"""
Generate static JSON data files from the Jolpica API (free, no API key).
Output goes to public/data/ — commit these files so the frontend
can serve them from Vercel's CDN without any backend calls.

Usage:
    python scripts/generate_static_data.py
    python scripts/generate_static_data.py --results-from 2018   # race results from a year
    python scripts/generate_static_data.py --year 2024           # refresh one year only
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


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------

def write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def run(years: list[int], results_from: int):
    connector = aiohttp.TCPConnector(limit=5)   # polite concurrency
    async with aiohttp.ClientSession(connector=connector) as session:

        for year in years:
            log.info("Year %d …", year)

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
    args = parser.parse_args()

    import datetime
    current_year = datetime.datetime.now().year
    years = [args.year] if args.year else list(range(args.standings_from, current_year + 1))

    asyncio.run(run(years, results_from=args.results_from))
