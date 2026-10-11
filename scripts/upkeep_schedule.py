"""
When the scheduled data upkeep (.github/workflows/data-upkeep.yml) should run. Stdlib only, so the
many runs with nothing to do finish in seconds without installing anything.

The workflow fires every 15 minutes; this says yes
  - from each session's start until 4 hours after it (the race 6): the session is stored once OpenF1
    publishes it, ~15 minutes after the flag — or from Jolpica, within hours, while the next session
    has OpenF1 shut;
  - for the first half hour of 00, 06, 12 and 18 UTC: everything else data upkeep does (older gaps,
    weather, stewards' decisions, the title race's track record) plus the results refresh (post-race
    penalties) — and Supabase sees activity, so the free project never pauses.
If the calendar (Jolpica: every session's start, in UTC) can't be read it says yes: a run with
nothing new is cheap.

Prints GitHub Actions outputs (`>> "$GITHUB_OUTPUT"`): run=true|false and results_refresh=true|false;
the reason goes to stderr, i.e. the log.

    python scripts/upkeep_schedule.py
"""
import json
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

CALENDAR_URL = "https://api.jolpi.ca/ergast/f1/current.json?limit=100"
SESSIONS = ("FirstPractice", "SecondPractice", "ThirdPractice", "SprintQualifying", "SprintShootout",
            "Sprint", "Qualifying")
AFTER_SESSION = timedelta(hours=4)
AFTER_RACE = timedelta(hours=6)
UPKEEP_HOURS = (0, 6, 12, 18)          # UTC
UPKEEP_MINUTES = 30                     # GitHub's schedule runs late at times: room for a run or two


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


def decide(now: datetime, calendar: Optional[List[Dict[str, Any]]]) -> Tuple[bool, bool, str]:
    """(run the upkeep, include the results refresh, why)."""
    if now.hour in UPKEEP_HOURS and now.minute < UPKEEP_MINUTES:
        return True, True, "the 6-hourly data upkeep"
    if calendar is None:
        return True, False, "the calendar couldn't be read"
    for label, start, end in windows(calendar):
        if start <= now <= end:
            return True, False, label
    return False, False, "nothing to pick up now"


def fetch_calendar() -> Optional[List[Dict[str, Any]]]:
    try:
        with urllib.request.urlopen(CALENDAR_URL, timeout=30) as response:
            return json.load(response)["MRData"]["RaceTable"]["Races"]
    except Exception as exc:                        # noqa: BLE001 — any failure: run anyway
        print(f"couldn't read the calendar: {exc}", file=sys.stderr)
        return None


def main() -> int:
    run, refresh, reason = decide(datetime.now(timezone.utc), fetch_calendar())
    print(f"{'Running' if run else 'Skipping'} data upkeep: {reason}.", file=sys.stderr)
    print(f"run={'true' if run else 'false'}")
    print(f"results_refresh={'true' if refresh else 'false'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
