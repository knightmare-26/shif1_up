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

# FastF1 session identifier -> our session_type column value.
SESSION_TYPE_MAP = {
    "R": "race", "S": "sprint", "Q": "qualifying", "SQ": "sprint_qualifying",
    "FP1": "fp1", "FP2": "fp2", "FP3": "fp3",
}

# Practice sessions have no classified Position/Time in FastF1's
# session.results (every row is NaN) — drivers aren't ranked by
# championship rules, only by their best lap, so these need lap data
# instead of the results table the other session types use.
PRACTICE_SESSIONS = {"FP1", "FP2", "FP3"}


def _extract_classified_results(fastf1_session, session: str) -> List[dict]:
    """R / S / Q / SQ all populate session.results with real Position data —
    same shape, so one extraction path handles all four. Q/SQ leave Time
    empty (quali has no single "race time"); Q1/Q2/Q3 is used instead,
    preferring the latest round a driver reached."""
    results = []
    for _, row in fastf1_session.results.iterrows():
        pos = row.get("Position")
        grid = row.get("GridPosition")
        grid_val = int(float(grid)) if pd.notna(grid) else None

        time_val = row.get("Time")
        time_str = str(time_val) if pd.notna(time_val) else ""
        if not time_str and session in ("Q", "SQ"):
            for q in ("Q3", "Q2", "Q1"):
                qt = row.get(q)
                if pd.notna(qt):
                    time_str = str(qt)
                    break

        laps_val = row.get("Laps")

        results.append({
            "position": int(pos) if pd.notna(pos) else 99,
            "driver_id": str(row.get("Abbreviation", "")).lower(),
            "constructor_id": str(row.get("TeamId", row.get("TeamName", ""))).lower().replace(" ", "_"),
            "grid": grid_val,
            "points": float(row.get("Points", 0)) if pd.notna(row.get("Points")) else 0.0,
            "time": time_str,
            "fastest_lap": bool(row.get("FastestLap", False)),
            "fastest_lap_time": str(row.get("FastestLapTime", "")) if pd.notna(row.get("FastestLapTime")) else "",
            "status": str(row.get("Status", "")) if pd.notna(row.get("Status")) else "",
            "laps_completed": int(laps_val) if pd.notna(laps_val) else None,
        })
    return results


def _extract_practice_results(fastf1_session) -> List[dict]:
    """No classification exists for practice — rank by each driver's best
    lap of the session instead. Driver/team metadata still comes from
    session.results (populated even though Position/Time aren't)."""
    laps = fastf1_session.laps
    if laps is None or laps.empty:
        return []

    best_laps = laps.dropna(subset=["LapTime"]).groupby("Driver")["LapTime"].min().sort_values()
    rank_by_driver = {drv: i + 1 for i, drv in enumerate(best_laps.index)}
    lap_counts = laps.groupby("Driver")["LapNumber"].count()

    results = []
    for _, row in fastf1_session.results.iterrows():
        abbr = str(row.get("Abbreviation", ""))
        position = rank_by_driver.get(abbr)
        if position is None:
            continue  # driver set no timed lap all session
        best_time = best_laps.get(abbr)
        time_str = str(best_time) if pd.notna(best_time) else ""
        results.append({
            "position": position,
            "driver_id": abbr.lower(),
            "constructor_id": str(row.get("TeamId", row.get("TeamName", ""))).lower().replace(" ", "_"),
            "grid": None,
            "points": 0.0,
            "time": time_str,
            "laps_completed": int(lap_counts.get(abbr, 0)),
            "fastest_lap": position == 1,
            "fastest_lap_time": time_str,
            "status": "",
        })
    return results


async def ingest_single_race(db, year: int, event: Union[int, str], include_laps: bool = False,
                              session: str = "R") -> dict:
    """Fetch and persist one session's results (and optionally laps) into `db`.

    `event` is anything FastF1's `get_session(year, event, session)` accepts —
    a round number or a GP name string. `session` is one of "R" (race), "S"
    (sprint), "Q" (qualifying), "SQ" (sprint qualifying), "FP1"/"FP2"/"FP3"
    (practice) — all share the same race_id, stored under a separate
    session_type so none of them collide. Returns a small summary dict.
    """
    import fastf1

    session_type = SESSION_TYPE_MAP.get(session, "race")
    is_practice = session in PRACTICE_SESSIONS
    loop = asyncio.get_event_loop()

    def _load():
        s = fastf1.get_session(year, event, session)
        # Practice needs lap data regardless of include_laps — that's the
        # only way to rank drivers when there's no classified session.results.
        s.load(laps=include_laps or is_practice, telemetry=False, weather=False, messages=False)
        return s

    fastf1_session = await loop.run_in_executor(None, _load)

    gp = str(getattr(fastf1_session, "event", {}).get("EventName", str(event))).replace(" Grand Prix", "").strip()
    race_id = f"{year}_{gp}"
    round_n = int(getattr(fastf1_session, "event", {}).get("RoundNumber", 0))

    if fastf1_session.results is None or fastf1_session.results.empty:
        return {"race_id": race_id, "stored": False, "reason": "no results available"}

    await db.store_races([{
        "race_id": race_id,
        "year": year,
        "round": round_n,
        "gp": gp,
        "date": str(getattr(fastf1_session, "event", {}).get("Session5Date", getattr(fastf1_session, "event", {}).get("EventDate", "")))[:10],
        "circuit_name": str(getattr(fastf1_session, "event", {}).get("Location", "")),
        "country": str(getattr(fastf1_session, "event", {}).get("Country", "")),
    }])

    drivers_seen: dict = {}
    constructors_seen: dict = {}
    for _, row in fastf1_session.results.iterrows():
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

    if is_practice:
        results = _extract_practice_results(fastf1_session)
        if not results:
            return {"race_id": race_id, "stored": False, "reason": "no lap data available"}
    else:
        results = _extract_classified_results(fastf1_session, session)

    await db.store_drivers(list(drivers_seen.values()))
    await db.store_constructors(list(constructors_seen.values()))
    await db.store_race_results(race_id, results, session_type=session_type)

    laps_stored = 0
    # Laps aren't keyed by session_type — skip for anything but the main race
    # to avoid colliding with its lap numbers under the same race_id.
    if include_laps and session_type == "race" and fastf1_session.laps is not None and not fastf1_session.laps.empty:
        laps_data = []
        for _, lap in fastf1_session.laps.iterrows():
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


async def run_ingest(duckdb_service, years: List[int], include_laps: bool = False,
                      include_practice: bool = False):
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
                await ingest_single_race(duckdb_service, year, round_n, include_laps, session="R")
            except Exception as e:
                logger.warning("Skipping %s round %s: %s", year, round_n, e)
            # Most rounds aren't a sprint weekend — this just no-ops for them.
            try:
                await ingest_single_race(duckdb_service, year, round_n, False, session="S")
            except Exception as e:
                logger.debug("No sprint for %s round %s: %s", year, round_n, e)

            # Off by default: practice forces lap loading, meaningfully increasing
            # fetch volume and time — an explicit opt-in, not part of a routine ingest.
            if include_practice:
                for fp_session in ("FP1", "FP2", "FP3"):
                    try:
                        await ingest_single_race(duckdb_service, year, round_n, False, session=fp_session)
                    except Exception as e:
                        logger.debug("No %s for %s round %s: %s", fp_session, year, round_n, e)

            status["races_done"] += 1

    status.update({"running": False, "message": "Done", "error": None})
    logger.info("Ingest complete for years %s", years)
