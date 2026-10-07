"""
A session's classification from OpenF1's `session_result` (free for finished sessions, 2023 on).

FastF1 has no sprint-qualifying classification: its results come from the Jolpica/Ergast feed,
which doesn't cover sprint qualifying, so every driver's position and Q1/Q2/Q3 time is empty and
the ingest stored them in feed order — 2024 China had Stroll on pole (Norris took it). Best laps
don't give the order either (a knockout, often in changing weather). OpenF1's session result does.
"""
import logging
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from services.driver_names import tidy_full_name
from services.openf1_live import OpenF1Client, find_session
from services.weekend_practice import team_id_for

logger = logging.getLogger(__name__)


def _last_duration(duration: Any) -> Optional[float]:
    """Q1/Q2/Q3 come as a list: the latest segment the driver set a time in (like the FastF1 rows)."""
    if isinstance(duration, (int, float)):
        return float(duration)
    if isinstance(duration, list):
        times = [d for d in duration if isinstance(d, (int, float))]
        return float(times[-1]) if times else None
    return None


async def classified_rows(client: OpenF1Client, session_key: int, teams: Dict[str, str],
                          constructor_names: Dict[str, str]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """(result rows, driver rows) shaped like ingest_service's. `teams` (driver_id -> constructor_id)
    are the weekend's known teams; otherwise OpenF1's team name is matched to `constructor_names`."""
    results = await client.get("session_result", session_key=session_key)
    drivers = {d.get("driver_number"): d for d in await client.get("drivers", session_key=session_key)}
    rows, people = [], []
    ranked = sorted(results, key=lambda r: (r.get("position") is None, r.get("position") or 0))
    for i, r in enumerate(ranked, start=1):
        info = drivers.get(r.get("driver_number")) or {}
        code = (info.get("name_acronym") or "").lower()
        if not code:
            continue
        seconds = _last_duration(r.get("duration"))
        status = "DSQ" if r.get("dsq") else "DNS" if r.get("dns") else "DNF" if r.get("dnf") else ""
        rows.append({
            "position": int(r["position"]) if r.get("position") else i,   # unclassified after the classified
            "driver_id": code,
            "constructor_id": teams.get(code) or team_id_for(info.get("team_name"), constructor_names) or "",
            "grid": None, "points": 0.0,
            "time": str(pd.Timedelta(seconds=seconds)) if seconds else "",
            "fastest_lap": False, "fastest_lap_time": "", "status": status,
            "laps_completed": r.get("number_of_laps"),
        })
        if info.get("full_name"):
            people.append({"driver_id": code, "full_name": tidy_full_name(info["full_name"]),
                           "number": info.get("driver_number")})
    return rows, people


async def weekend_teams(db, race_id: str) -> Dict[str, str]:
    """driver_id -> constructor_id from the weekend's stored sessions."""
    teams: Dict[str, str] = {}
    for session_type in ("fp1", "fp2", "fp3", "sprint", "qualifying", "race"):
        for row in await db.get_race_results(race_id, session_type):
            if row.get("constructor_id") and row["constructor_id"] not in ("nan", "none"):
                teams[row["driver_id"]] = row["constructor_id"]
    return teams


async def openf1_session_rows(db, year: int, gp: str, code: str, race_id: str,
                              client: Optional[OpenF1Client] = None) -> List[Dict[str, Any]]:
    """One session's classified rows from OpenF1 ([] if it has none). Stores no drivers."""
    own = client is None
    client = client or OpenF1Client(creds={})
    try:
        session = await find_session(client, year, gp, code)
        if session is None:
            return []
        rows, _ = await classified_rows(client, session["session_key"], await weekend_teams(db, race_id), {})
        return rows
    finally:
        if own:
            await client.close()
