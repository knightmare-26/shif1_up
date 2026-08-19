"""
Ingest Service — runs inside the FastAPI process so it reuses the existing
DuckDB connection and avoids file-locking conflicts with the API.
"""

import asyncio
import logging
import pandas as pd
from typing import List, Union

logger = logging.getLogger(__name__)

# Shared status dict — polled by GET /admin/ingest/status
status = {
    "running": False,
    "message": "Idle",
    "races_done": 0,
    "races_total": 0,
    "error": None,
}


async def ingest_single_race(db, year: int, event: Union[int, str], include_laps: bool = False) -> dict:
    """Fetch and persist one race's results (and optionally laps) into `db`.

    `event` is anything FastF1's `get_session(year, event, "R")` accepts —
    a round number or a GP name string. Returns a small summary dict.
    """
    import fastf1

    loop = asyncio.get_event_loop()

    def _load():
        s = fastf1.get_session(year, event, "R")
        s.load(laps=include_laps, telemetry=False, weather=False, messages=False)
        return s

    session = await loop.run_in_executor(None, _load)

    gp = str(getattr(session, "event", {}).get("EventName", str(event))).replace(" Grand Prix", "").strip()
    race_id = f"{year}_{gp}"
    round_n = int(getattr(session, "event", {}).get("RoundNumber", 0))

    if session.results is None or session.results.empty:
        return {"race_id": race_id, "stored": False, "reason": "no results available"}

    await db.store_races([{
        "race_id": race_id,
        "year": year,
        "round": round_n,
        "gp": gp,
        "date": str(getattr(session, "event", {}).get("Session5Date", getattr(session, "event", {}).get("EventDate", "")))[:10],
        "circuit_name": str(getattr(session, "event", {}).get("Location", "")),
        "country": str(getattr(session, "event", {}).get("Country", "")),
    }])

    drivers_seen: dict = {}
    constructors_seen: dict = {}
    results = []
    for _, row in session.results.iterrows():
        driver_id = str(row.get("Abbreviation", "")).lower()
        constructor_id = str(row.get("TeamId", row.get("TeamName", ""))).lower().replace(" ", "_")
        drivers_seen[driver_id] = {
            "driver_id": driver_id,
            "full_name": f"{row.get('FirstName','')} {row.get('LastName','')}".strip(),
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
        grid_val = int(float(grid)) if pd.notna(grid) else None
        results.append({
            "position": int(pos) if pd.notna(pos) else 99,
            "driver_id": driver_id,
            "constructor_id": constructor_id,
            "grid": grid_val,
            "points": float(row.get("Points", 0)),
            "time": str(row.get("Time", "")),
            "fastest_lap": bool(row.get("FastestLap", False)),
            "fastest_lap_time": str(row.get("FastestLapTime", "")),
            "status": str(row.get("Status", "")),
        })

    await db.store_drivers(list(drivers_seen.values()))
    await db.store_constructors(list(constructors_seen.values()))
    await db.store_race_results(race_id, results)

    laps_stored = 0
    if include_laps and session.laps is not None and not session.laps.empty:
        laps_data = []
        for _, lap in session.laps.iterrows():
            if not pd.notna(lap.get("LapTime")):
                continue
            laps_data.append({
                "driver_id": str(lap.get("Driver", "")).lower(),
                "lap_number": int(lap.get("LapNumber", 0)),
                "lap_time_ms": int(lap["LapTime"].total_seconds() * 1000),
                "sector1_ms": int(lap["Sector1Time"].total_seconds() * 1000) if pd.notna(lap.get("Sector1Time")) else None,
                "sector2_ms": int(lap["Sector2Time"].total_seconds() * 1000) if pd.notna(lap.get("Sector2Time")) else None,
                "sector3_ms": int(lap["Sector3Time"].total_seconds() * 1000) if pd.notna(lap.get("Sector3Time")) else None,
                "tyre": str(lap.get("Compound", "")),
                "pit": bool(pd.notna(lap.get("PitOutTime"))),
                "position": int(lap["Position"]) if pd.notna(lap.get("Position")) else None,
            })
        if laps_data:
            await db.store_laps(race_id, laps_data)
            laps_stored = len(laps_data)

    return {"race_id": race_id, "stored": True, "results": len(results), "laps": laps_stored}


async def run_ingest(duckdb_service, years: List[int], include_laps: bool = False):
    """Ingest one or more seasons into the supplied DB service instance."""
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

        rounds = [int(row.get("RoundNumber", 0)) for _, row in schedule.iterrows()]
        status["races_total"] += len(rounds)

        for round_n in rounds:
            status["message"] = f"Processing {year} round {round_n}…"
            try:
                await ingest_single_race(duckdb_service, year, round_n, include_laps)
            except Exception as e:
                logger.warning("Skipping %s round %s: %s", year, round_n, e)
            status["races_done"] += 1

    status.update({"running": False, "message": "Done", "error": None})
    logger.info("Ingest complete for years %s", years)
