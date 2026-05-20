"""
Ingest Service — runs inside the FastAPI process so it reuses the existing
DuckDB connection and avoids file-locking conflicts with the API.
"""

import asyncio
import logging
import pandas as pd
from typing import List

logger = logging.getLogger(__name__)

# Shared status dict — polled by GET /admin/ingest/status
status = {
    "running": False,
    "message": "Idle",
    "races_done": 0,
    "races_total": 0,
    "error": None,
}


async def run_ingest(duckdb_service, years: List[int], include_laps: bool = False):
    """Ingest one or more seasons into the supplied DuckDB service instance."""
    global status
    status.update({"running": True, "error": None, "races_done": 0, "races_total": 0})

    try:
        import fastf1
    except ImportError:
        status.update({"running": False, "error": "FastF1 not installed"})
        return

    loop = asyncio.get_event_loop()

    for year in years:
        status["message"] = f"Fetching {year} race schedule…"
        try:
            schedule = await loop.run_in_executor(
                None, lambda y=year: fastf1.get_event_schedule(y, include_testing=False)
            )
        except Exception as e:
            status.update({"running": False, "error": f"Schedule fetch failed for {year}: {e}"})
            return

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

        await duckdb_service.store_races(races)
        status["races_total"] += len(races)

        drivers_seen: dict = {}
        constructors_seen: dict = {}

        for race in races:
            race_id = race["race_id"]
            round_n = race["round"]
            status["message"] = f"Processing {race_id}…"

            try:
                def _load(yr=year, rnd=round_n):
                    s = fastf1.get_session(yr, rnd, "R")
                    s.load(laps=include_laps, telemetry=False, weather=False, messages=False)
                    return s

                session = await loop.run_in_executor(None, _load)

                if session.results is None or session.results.empty:
                    status["races_done"] += 1
                    continue

                results = []
                for _, row in session.results.iterrows():
                    driver_id = str(row.get("Abbreviation", "")).lower()
                    constructor_id = (
                        str(row.get("TeamId", row.get("TeamName", "")))
                        .lower()
                        .replace(" ", "_")
                    )
                    drivers_seen[driver_id] = {
                        "driver_id": driver_id,
                        "full_name": f"{row.get('FirstName','')} {row.get('LastName','')}".strip(),
                        "nationality": str(row.get("CountryCode", "")),
                        "number": int(row.get("DriverNumber", 0))
                        if pd.notna(row.get("DriverNumber"))
                        else 0,
                    }
                    constructors_seen[constructor_id] = {
                        "constructor_id": constructor_id,
                        "constructor_name": str(row.get("TeamName", "")),
                        "nationality": "",
                    }
                    pos  = row.get("Position")
                    grid = row.get("GridPosition")
                    grid_val = int(float(grid)) if pd.notna(grid) else None
                    results.append({
                        "position":        int(pos) if pd.notna(pos) else 99,
                        "driver_id":       driver_id,
                        "constructor_id":  constructor_id,
                        "grid":            grid_val,
                        "points":          float(row.get("Points", 0)),
                        "time":            str(row.get("Time", "")),
                        "fastest_lap":     bool(row.get("FastestLap", False)),
                        "fastest_lap_time": str(row.get("FastestLapTime", "")),
                        "status":          str(row.get("Status", "")),
                    })

                await duckdb_service.store_race_results(race_id, results)

                if include_laps and session.laps is not None and not session.laps.empty:
                    laps_data = []
                    for _, lap in session.laps.iterrows():
                        if not pd.notna(lap.get("LapTime")):
                            continue
                        laps_data.append({
                            "driver_id": str(lap.get("Driver", "")).lower(),
                            "lap_number": int(lap.get("LapNumber", 0)),
                            "lap_time_ms": int(lap["LapTime"].total_seconds() * 1000),
                            "sector1_ms": int(lap["Sector1Time"].total_seconds() * 1000)
                            if pd.notna(lap.get("Sector1Time")) else None,
                            "sector2_ms": int(lap["Sector2Time"].total_seconds() * 1000)
                            if pd.notna(lap.get("Sector2Time")) else None,
                            "sector3_ms": int(lap["Sector3Time"].total_seconds() * 1000)
                            if pd.notna(lap.get("Sector3Time")) else None,
                            "tyre": str(lap.get("Compound", "")),
                            "pit": bool(pd.notna(lap.get("PitOutTime"))),
                            "position": int(lap["Position"]) if pd.notna(lap.get("Position")) else None,
                        })
                    if laps_data:
                        await duckdb_service.store_laps(race_id, laps_data)

            except Exception as e:
                logger.warning("Skipping %s: %s", race_id, e)

            status["races_done"] += 1

        if drivers_seen:
            await duckdb_service.store_drivers(list(drivers_seen.values()))
        if constructors_seen:
            await duckdb_service.store_constructors(list(constructors_seen.values()))

    status.update({"running": False, "message": "Done", "error": None})
    logger.info("Ingest complete for years %s", years)
