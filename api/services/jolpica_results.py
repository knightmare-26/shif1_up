"""
A weekend's finished qualifying, sprint or race from Jolpica (the Ergast successor): the weekend
loader's fallback when OpenF1 is shut or failing.

OpenF1 closes all free access while any F1 session is live, and Render's free server sleeps between
visits, so the loader often only runs when someone opens the site — around the sessions, while
OpenF1 is locked. Singapore 2026: the server slept through Saturday and woke in Sunday's race lock,
so the sprint and qualifying never reached Predicted vs Actual and the title race was missing the
sprint points. Jolpica isn't locked and publishes these classifications within hours: Q1-Q3 times,
and for a race or sprint the official grid (penalties applied, a pit-lane start as 0, like FastF1's),
points and status. Its constructor ids and driver codes are ours. It has no sprint qualifying.
"""
import logging
from typing import Any, Dict, List, Optional, Tuple

import httpx
import pandas as pd

logger = logging.getLogger(__name__)

JOLPICA_URL = "https://api.jolpi.ca/ergast/f1"
# session type -> (Jolpica endpoint, the list in its race entry)
SESSIONS = {"qualifying": ("qualifying", "QualifyingResults"), "sprint": ("sprint", "SprintResults"),
            "race": ("results", "Results")}


def lap_seconds(text: Optional[str]) -> Optional[float]:
    """'1:31.373' or '58.123' -> seconds."""
    if not text:
        return None
    minutes, _, seconds = str(text).rpartition(":")
    try:
        return (int(minutes) * 60 if minutes else 0) + float(seconds)
    except ValueError:
        return None


def _int(value: Any) -> Optional[int]:
    return int(value) if str(value or "").isdigit() else None


def rows_from(results: List[Dict[str, Any]], session_type: str,
              teams: Dict[str, str]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """(result rows, driver rows) shaped like ingest_service's and openf1_results'. `teams`
    (driver_id -> constructor_id) are the weekend's known teams; else Jolpica's constructor id."""
    race = session_type != "qualifying"
    rows, people = [], []
    ranked = sorted(results, key=lambda r: _int(r.get("position")) or 999)
    for i, r in enumerate(ranked, start=1):
        driver = r.get("Driver") or {}
        code = (driver.get("code") or "").lower()
        if not code:
            continue
        if race:
            millis = _int((r.get("Time") or {}).get("millis"))           # finishers on the lead lap
            time = str(pd.Timedelta(milliseconds=millis)) if millis else ""
            status, grid = r.get("status") or "", _int(r.get("grid"))
        else:
            # The latest segment the driver set a time in, like the FastF1 and OpenF1 rows.
            best = next((s for s in (lap_seconds(r.get(q)) for q in ("Q3", "Q2", "Q1")) if s), None)
            time = str(pd.Timedelta(seconds=best)) if best else ""
            status, grid = "", None
        rows.append({
            "position": _int(r.get("position")) or i,
            "driver_id": code,
            "constructor_id": teams.get(code) or (r.get("Constructor") or {}).get("constructorId") or "",
            "grid": grid,
            "points": float(r.get("points") or 0.0) if race else 0.0,
            "time": time, "fastest_lap": False, "fastest_lap_time": "", "status": status,
            "laps_completed": _int(r.get("laps")),
        })
        name = " ".join(filter(None, (driver.get("givenName"), driver.get("familyName"))))
        if name:
            people.append({"driver_id": code, "full_name": name, "number": _int(driver.get("permanentNumber"))})
    return rows, people


async def session_rows(year: int, round_no: int, session_type: str, teams: Dict[str, str],
                       transport: Optional[httpx.AsyncBaseTransport] = None
                       ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """One session's rows ([] until Jolpica has its classification). Raises if Jolpica can't be reached."""
    endpoint, key = SESSIONS[session_type]
    async with httpx.AsyncClient(timeout=15, transport=transport) as http:
        response = await http.get(f"{JOLPICA_URL}/{year}/{round_no}/{endpoint}.json", params={"limit": 100})
        response.raise_for_status()
    races = response.json()["MRData"]["RaceTable"]["Races"]
    return rows_from(races[0].get(key) or [], session_type, teams) if races else ([], [])
