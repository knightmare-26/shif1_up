"""
Load each race weekend's practice (FP1-3) and qualifying (sprint qualifying, qualifying) as they
finish, from OpenF1 (Phase 1 #30, Phase 2 #31).

Predictions use the weekend's practice pace once it's stored (services/practice_features.py), but
practice was only ever stored by hand (`POST /admin/ingest` with practice, or
scripts/backfill_practice.py) — so a live prediction almost never had it. OpenF1 serves finished
sessions for free, and a practice session's laps and drivers are two small requests, far lighter
than FastF1's full session load on the free server.

Practice rows are stored the way ingest_service._extract_practice_results stores FastF1's: ranked by
best lap, the lap as a timedelta string, driver ids from the three-letter code. Qualifying comes from
OpenF1's classification (services/openf1_results.py), so a race predicted after qualifying starts from
the real qualifying order (the results refresh only fetches qualifying after the race). OpenF1 shuts free access
while any session is live (OpenF1Locked) — the loader stops and tries again later.
"""
import logging
import unicodedata
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import pandas as pd

from services.driver_names import tidy_full_name
from services.openf1_live import OpenF1Client, OpenF1Locked, find_session, parse_time

logger = logging.getLogger(__name__)

PRACTICE = {"FP1": "fp1", "FP2": "fp2", "FP3": "fp3"}
QUALIFYING = {"SQ": "sprint_qualifying", "Q": "qualifying"}
# Races too, so a finished session moves to Predicted vs Actual straight away; the starting order
# is the session that set it (OpenF1 has no grid), until FastF1's official results replace it.
RACES = {"S": ("sprint", "sprint_qualifying"), "R": ("race", "qualifying")}
DAYS_BEFORE_RACE = 4          # FP1 is two days before the race; a little slack for odd calendars
DAYS_AFTER_RACE = 14          # and fill in a recent weekend that was missed
SETTLE_MINUTES = 15           # let OpenF1 finish publishing a session's laps
MIN_DRIVERS = 10              # fewer isn't a whole session


def _norm(text: Optional[str]) -> str:
    text = "".join(c for c in unicodedata.normalize("NFD", text or "") if not unicodedata.combining(c))
    return " ".join(text.replace("_", " ").casefold().replace(" f1 team", "").split())


def team_id_for(team_name: Optional[str], constructor_names: Dict[str, str]) -> Optional[str]:
    """Our constructor id for an OpenF1 team name. Names differ in their suffixes ("Red Bull
    Racing" vs "Red Bull Racing Honda RBPT"), so a name that starts the other one also matches."""
    wanted = _norm(team_name)
    if not wanted:
        return None
    names = {_norm(name): cid for cid, name in constructor_names.items() if name}
    if wanted in names:
        return names[wanted]
    starts = [cid for name, cid in names.items() if name.startswith(wanted + " ") or wanted.startswith(name + " ")]
    return starts[0] if len(starts) == 1 else None


def _race_day(race: Dict[str, Any]) -> Optional[date]:
    try:
        return date.fromisoformat(str(race.get("date") or "")[:10])
    except ValueError:
        return None


def weekends_to_check(races: List[Dict[str, Any]], today: date) -> List[Dict[str, Any]]:
    """Rounds whose practice could be running now or was recently missed."""
    return [r for r in races if (day := _race_day(r))
            and day - timedelta(days=DAYS_BEFORE_RACE) <= today <= day + timedelta(days=DAYS_AFTER_RACE)]


async def session_rows(client: OpenF1Client, session_key: int, constructor_names: Dict[str, str],
                       last_teams: Dict[str, str]) -> tuple:
    """(result rows, driver rows) for one finished practice session."""
    laps = await client.get("laps", session_key=session_key)
    drivers = {d.get("driver_number"): d for d in await client.get("drivers", session_key=session_key)}
    best: Dict[Any, float] = {}
    counts: Dict[Any, int] = {}
    for lap in laps:
        number = lap.get("driver_number")
        counts[number] = counts.get(number, 0) + 1
        seconds = lap.get("lap_duration")
        if seconds and not lap.get("is_pit_out_lap"):
            best[number] = min(best.get(number, float("inf")), float(seconds))

    rows, people = [], []
    for position, (number, seconds) in enumerate(sorted(best.items(), key=lambda kv: kv[1]), start=1):
        info = drivers.get(number) or {}
        code = (info.get("name_acronym") or "").lower()
        if not code:
            continue
        lap_time = str(pd.Timedelta(seconds=seconds))
        rows.append({
            "position": position, "driver_id": code,
            "constructor_id": team_id_for(info.get("team_name"), constructor_names) or last_teams.get(code) or "",
            "grid": None, "points": 0.0, "time": lap_time, "laps_completed": counts.get(number, 0),
            "fastest_lap": position == 1, "fastest_lap_time": lap_time, "status": "",
        })
        if info.get("full_name"):
            people.append({"driver_id": code, "full_name": tidy_full_name(info["full_name"]), "number": number})
    return rows, people


async def load_weekend_practice(db, client: OpenF1Client, constructor_names: Dict[str, str],
                                last_teams: Dict[str, str], now: Optional[datetime] = None) -> List[Dict[str, str]]:
    """Store every finished, not-yet-stored practice and qualifying session of the weekends around
    now. Returns the sessions stored (the caller retrains when there are any)."""
    from services.openf1_results import classified_rows, weekend_teams
    now = now or datetime.now(timezone.utc)
    today = now.date()
    stored: List[Dict[str, str]] = []
    races: List[Dict[str, Any]] = []
    for year in sorted({(today - timedelta(days=DAYS_AFTER_RACE)).year, today.year}):
        races += [{**r, "year": r.get("year", year)} for r in await db.get_races_by_year(year)]

    try:
        for race in weekends_to_check(races, today):
            for code, session_type in {**PRACTICE, **QUALIFYING, **{c: t for c, (t, _) in RACES.items()}}.items():
                if await db.get_race_results(race["race_id"], session_type):
                    continue
                session = await find_session(client, int(race["year"]), race.get("gp") or race["race_id"], code)
                if session is None:
                    continue                                # a sprint weekend has no FP2/FP3
                ended = parse_time(session.get("date_end"))
                if ended is None or now < ended + timedelta(minutes=SETTLE_MINUTES):
                    continue
                if code in QUALIFYING:
                    teams = {**last_teams, **await weekend_teams(db, race["race_id"])}
                    rows, people = await classified_rows(client, session["session_key"], teams, constructor_names)
                elif code in RACES:
                    teams = {**last_teams, **await weekend_teams(db, race["race_id"])}
                    grid = {r["driver_id"]: int(r["position"])
                            for r in await db.get_race_results(race["race_id"], RACES[code][1])}
                    rows, people = await classified_rows(client, session["session_key"], teams, constructor_names,
                                                         race=True, grid=grid)
                else:
                    rows, people = await session_rows(client, session["session_key"], constructor_names, last_teams)
                if len(rows) < MIN_DRIVERS:
                    logger.info("weekend practice: %s %s has %d timed drivers so far", race["race_id"], code, len(rows))
                    continue
                await db.store_drivers(people, rename=False)        # adds a stand-in; keeps known names
                await db.store_race_results(race["race_id"], rows, session_type)
                logger.info("weekend sessions: stored %s %s (%d drivers)", race["race_id"], code, len(rows))
                stored.append({"race_id": race["race_id"], "session_type": session_type})
    except OpenF1Locked:
        logger.info("weekend practice: OpenF1 is locked while a session is live — trying again later")
    except Exception as exc:
        # Rate-limited, a timeout, a server error: what's already stored is still reported (so the
        # models retrain on it — the next check skips stored sessions and wouldn't say so again).
        logger.warning("weekend sessions: stopped after storing %d (%s); the rest at the next check", len(stored), exc)
    return stored


def check_again_in(races: List[Dict[str, Any]], today: date) -> int:
    """Seconds to the next check: every 20 minutes over a race weekend, else every 6 hours."""
    in_weekend = any((day := _race_day(r)) and day - timedelta(days=DAYS_BEFORE_RACE) <= today <= day for r in races)
    return 20 * 60 if in_weekend else 6 * 3600
