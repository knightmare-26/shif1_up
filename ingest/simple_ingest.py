#!/usr/bin/env python3
"""
Fast F1 Data Ingest
Populates DuckDB with race schedules, race results, drivers, and constructors
using FastF1 session results only — no telemetry download, runs in minutes.

Usage:
    python ingest/simple_ingest.py --years 2024
    python ingest/simple_ingest.py --years 2023 2024
"""

import asyncio
import argparse
import logging
import os
import sys
from pathlib import Path

# Make api/ importable
sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("FASTF1_CACHE_DIR", "data/fastf1_cache")
os.environ.setdefault("DUCKDB_PATH", "data/f1_history.duckdb")

import fastf1
import fastf1.ergast
import pandas as pd

from api.services.simple_duckdb_service import SimpleDuckDBService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

CACHE_DIR = os.getenv("FASTF1_CACHE_DIR", "data/fastf1_cache")
DB_PATH   = os.getenv("DUCKDB_PATH", "data/f1_history.duckdb")


def setup_fastf1():
    Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(CACHE_DIR)
    logger.info("FastF1 cache: %s", CACHE_DIR)


async def ingest_year(year: int, db: SimpleDuckDBService, include_laps: bool = False):
    logger.info("=== Ingesting %d ===", year)
    loop = asyncio.get_event_loop()

    # --- Race schedule (sync FastF1 call, run in executor) ---
    try:
        schedule = await loop.run_in_executor(
            None, lambda: fastf1.get_event_schedule(year, include_testing=False)
        )
        races = []
        for _, row in schedule.iterrows():
            gp = str(row.get("EventName", "")).replace(" Grand Prix", "").strip()
            races.append({
                "race_id": f"{year}_{gp}",
                "year": year,
                "round": int(row.get("RoundNumber", 0)),
                "gp": gp,
                "date": str(row.get("Session5Date", row.get("EventDate", "")))[:10],
                "circuit_name": str(row.get("Location", "")),
                "country": str(row.get("Country", "")),
            })
        await db.store_races(races)
        logger.info("Stored %d races for %d", len(races), year)
    except Exception as e:
        logger.error("Race schedule failed for %d: %s", year, e)
        return

    # --- Per-race results ---
    drivers_seen: dict = {}
    constructors_seen: dict = {}

    for race in races:
        race_id = race["race_id"]
        round_n = race["round"]
        logger.info("  Processing %s ...", race_id)
        try:
            def _load_session(yr, rnd):
                s = fastf1.get_session(yr, rnd, "R")
                s.load(laps=include_laps, telemetry=False, weather=False, messages=False)
                return s

            session = await loop.run_in_executor(None, _load_session, year, round_n)

            if session.results is None or session.results.empty:
                logger.warning("  No results for %s", race_id)
                continue

            results = []
            for _, row in session.results.iterrows():
                driver_id      = str(row.get("Abbreviation", "")).lower()
                constructor_id = str(row.get("TeamId", row.get("TeamName", ""))).lower().replace(" ", "_")

                drivers_seen[driver_id] = {
                    "driver_id": driver_id,
                    "full_name": f"{row.get('FirstName', '')} {row.get('LastName', '')}".strip(),
                    "nationality": str(row.get("CountryCode", "")),
                    "number": int(row.get("DriverNumber", 0)) if pd.notna(row.get("DriverNumber")) else 0,
                }
                constructors_seen[constructor_id] = {
                    "constructor_id": constructor_id,
                    "constructor_name": str(row.get("TeamName", "")),
                    "nationality": "",
                }

                pos = row.get("Position")
                grid = row.get("GridPosition")
                results.append({
                    "position": int(pos) if pd.notna(pos) else 99,
                    "driver_id": driver_id,
                    "constructor_id": constructor_id,
                    "grid": int(grid) if pd.notna(grid) else None,
                    "points": float(row.get("Points", 0)),
                    "time": str(row.get("Time", "")),
                    "fastest_lap": bool(row.get("FastestLap", False)),
                    "fastest_lap_time": str(row.get("FastestLapTime", "")),
                    "status": str(row.get("Status", "")),
                })

            await db.store_race_results(race_id, results)
            logger.info("  Stored %d results for %s", len(results), race_id)

            # --- Lap data (optional) ---
            if include_laps and session.laps is not None and not session.laps.empty:
                laps_data = []
                for _, lap in session.laps.iterrows():
                    if not pd.notna(lap.get('LapTime')):
                        continue
                    laps_data.append({
                        'driver_id': str(lap.get('Driver', '')).lower(),
                        'lap_number': int(lap.get('LapNumber', 0)),
                        'lap_time_ms': int(lap['LapTime'].total_seconds() * 1000),
                        'sector1_ms': int(lap['Sector1Time'].total_seconds() * 1000) if pd.notna(lap.get('Sector1Time')) else None,
                        'sector2_ms': int(lap['Sector2Time'].total_seconds() * 1000) if pd.notna(lap.get('Sector2Time')) else None,
                        'sector3_ms': int(lap['Sector3Time'].total_seconds() * 1000) if pd.notna(lap.get('Sector3Time')) else None,
                        'tyre': str(lap.get('Compound', '')),
                        'pit': bool(pd.notna(lap.get('PitOutTime'))),
                        'position': int(lap['Position']) if pd.notna(lap.get('Position')) else None,
                    })
                if laps_data:
                    await db.store_laps(race_id, laps_data)
                    logger.info("  Stored %d laps for %s", len(laps_data), race_id)

        except Exception as e:
            logger.warning("  Skipping %s: %s", race_id, e)
            continue

    # --- Drivers & Constructors ---
    if drivers_seen:
        await db.store_drivers(list(drivers_seen.values()))
        logger.info("Stored %d drivers for %d", len(drivers_seen), year)

    if constructors_seen:
        await db.store_constructors(list(constructors_seen.values()))
        logger.info("Stored %d constructors for %d", len(constructors_seen), year)

    logger.info("=== Done %d ===", year)


async def main(years: list[int], include_laps: bool = False):
    db = SimpleDuckDBService(DB_PATH)
    await db.initialize()
    try:
        for year in years:
            await ingest_year(year, db, include_laps=include_laps)
    finally:
        await db.cleanup()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fast F1 data ingest into DuckDB")
    parser.add_argument("--years", nargs="+", type=int, default=[2024],
                        help="Season years to ingest (e.g. --years 2023 2024)")
    parser.add_argument("--laps", action="store_true",
                        help="Also ingest lap data (slower — downloads ~50MB per race)")
    args = parser.parse_args()

    setup_fastf1()
    asyncio.run(main(args.years, include_laps=args.laps))
