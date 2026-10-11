"""
Wake the API when there's new data to pick up, so the site keeps itself current without anyone
opening it.

Render's free web service sleeps after 15 minutes without a request, and everything that keeps the
data current — the weekend loader, data upkeep, the results refresh — runs inside it and catches up
the moment it starts. So it has to be woken when something new can be fetched. Run every 10 minutes
by .github/workflows/wake-api.yml, this decides from the season's calendar (Jolpica: every session's
start time, in UTC) whether now is such a time, and if so calls /health:

  - from each session's start until a few hours after it (practice, sprint qualifying, sprint and
    qualifying: 4 h; the race: 6 h). OpenF1 is shut while a session runs; the loader stores it ~15
    minutes after it ends, or Jolpica has it within hours;
  - for an hour every 6 hours (00, 06, 12 and 18 UTC): the results refresh (post-race penalties),
    data upkeep's batches (older gaps, weather, stewards' decisions) — and Supabase sees activity,
    so the free project never pauses.

That's ~4-5 hours a day plus ~20 per race weekend, well inside Render's 750 free hours a month. If
the calendar can't be read it wakes anyway (one cheap request). Stdlib only; never fails the
workflow (a failed scheduled run emails the repository owner).

    API_URL=https://… python scripts/wake_api.py      # wake if it's time
    python scripts/wake_api.py --check                 # only say whether it would
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

CALENDAR_URL = "https://api.jolpi.ca/ergast/f1/current.json?limit=100"
SESSIONS = ("FirstPractice", "SecondPractice", "ThirdPractice", "SprintQualifying", "SprintShootout",
            "Sprint", "Qualifying")
AFTER_SESSION = timedelta(hours=4)
AFTER_RACE = timedelta(hours=6)
UPKEEP_HOURS = (0, 6, 12, 18)          # UTC; the whole hour, so the start-up catch-up can finish


def _when(entry: Dict[str, Any]) -> Optional[datetime]:
    """A calendar entry's start ('2026-10-11' + '12:00:00Z') in UTC; None without a time."""
    if not entry.get("date") or not entry.get("time"):
        return None
    try:
        return datetime.fromisoformat(f"{entry['date']}T{entry['time'].rstrip('Z')}").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def windows(calendar: List[Dict[str, Any]]) -> List[Tuple[str, datetime, datetime]]:
    """(label, from, to) for every session of the season."""
    out = []
    for race in calendar:
        for name in SESSIONS:
            start = _when(race.get(name) or {})
            if start:
                out.append((f"{race.get('raceName')} {name}", start, start + AFTER_SESSION))
        start = _when(race)
        if start:
            out.append((f"{race.get('raceName')} race", start, start + AFTER_RACE))
    return out


def wake_reason(now: datetime, calendar: Optional[List[Dict[str, Any]]]) -> Optional[str]:
    """Why the API should be awake now, or None."""
    if calendar is None:
        return "the calendar couldn't be read"
    for label, start, end in windows(calendar):
        if start <= now <= end:
            return label
    if now.hour in UPKEEP_HOURS:
        return "the 6-hourly data upkeep"
    return None


def fetch_calendar() -> Optional[List[Dict[str, Any]]]:
    try:
        with urllib.request.urlopen(CALENDAR_URL, timeout=30) as response:
            return json.load(response)["MRData"]["RaceTable"]["Races"]
    except Exception as exc:                        # noqa: BLE001 — any failure: wake anyway
        print(f"::warning::couldn't read the calendar: {exc}")
        return None


def ping(api_url: str, attempts: int = 2) -> bool:
    """GET /health. A sleeping instance boots on the request (Render holds it meanwhile)."""
    url = api_url.rstrip("/") + "/health"
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(url, timeout=180) as response:
                body = json.load(response)
            print(f"API answered: {body.get('status')} (database: "
                  f"{(body.get('checks') or {}).get('database', {}).get('state', 'n/a')})")
            return True
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            print(f"attempt {attempt}: {exc}")
            if attempt < attempts:
                time.sleep(20)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="only say whether it would wake the API now")
    args = parser.parse_args()
    reason = wake_reason(datetime.now(timezone.utc), fetch_calendar())
    if reason is None:
        print("Nothing to pick up now; letting the API sleep.")
        return 0
    print(f"Waking the API: {reason}.")
    if args.check:
        return 0
    api_url = os.getenv("API_URL")
    if not api_url:
        print("::warning::API_URL isn't set (a repository secret) — can't wake the API.")
        return 0
    if not ping(api_url):
        print("::warning::the API didn't answer; the next run tries again.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
