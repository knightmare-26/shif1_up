"""
When the scheduled data upkeep (.github/workflows/data-upkeep.yml) runs, and how. Stdlib only, so a
run with nothing to do finishes in seconds without installing anything.

GitHub starts far fewer scheduled runs than asked for — every 15 minutes is asked; Oct 2026 it started
4-5 a day, 3-10 hours apart, at no fixed time (an earlier version only worked in the first half hour of
00/06/12/18 UTC, so all 23 runs of its first five days did nothing). So nothing here depends on a run
arriving at a particular time:

  - a normal day: a run updates (and re-fetches the last 14 days' results: post-race penalties)
    unless the last update was less than MIN_GAP ago — with GitHub's cadence that's every run;
  - a race weekend (from 30 minutes before its first session until WATCH after the race ends): a run
    stays on (`until`) and the job runs a pass every 15 minutes in the WATCH after each session's end
    (sessions are stored ~15-35 minutes after the flag, or from Jolpica within hours while OpenF1 is
    shut by the next session), waiting in between. Before GitHub's 6-hour job limit it starts the next
    run itself (`--still-weekend`), so a dropped trigger can't leave a session end unwatched.

Session times come from Jolpica's calendar (each session's start, UTC); the end is the start plus
LENGTH. If the calendar can't be read, a run updates once (`until` empty). The last update's time comes
from GitHub's record of this workflow's runs (GITHUB_TOKEN); if it can't be read, a run updates.

    python scripts/upkeep_schedule.py                 # outputs: run, results_refresh, until
    python scripts/upkeep_schedule.py --still-weekend # exit 0 if a race weekend is still under way
"""
import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

CALENDAR_URL = "https://api.jolpi.ca/ergast/f1/current.json?limit=100"
WORKFLOW = "data-upkeep.yml"
UPDATE_STEP = "Update the data in Supabase"          # the workflow step that does the work
# How long each session runs (red flags aside), from its scheduled start.
LENGTH = {"FirstPractice": 60, "SecondPractice": 60, "ThirdPractice": 60, "SprintQualifying": 45,
          "SprintShootout": 45, "Sprint": 60, "Qualifying": 60, "race": 120}
WATCH = timedelta(hours=2, minutes=30)     # checked every 15 minutes this long after a session ends
BEFORE_WEEKEND = timedelta(minutes=30)
MIN_GAP = timedelta(hours=3)               # a normal day: at most one update this often
MAX_RUN = timedelta(hours=5, minutes=40)   # GitHub stops a job at 6 hours (installing takes a minute or two)

Session = Tuple[str, datetime, datetime]   # (label, start, end)


def _when(entry: Dict[str, Any]) -> Optional[datetime]:
    """A calendar entry's start ('2026-10-11' + '12:00:00Z') in UTC; None without a time."""
    if not entry.get("date") or not entry.get("time"):
        return None
    try:
        return datetime.fromisoformat(f"{entry['date']}T{entry['time'].rstrip('Z')}").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def sessions(race: Dict[str, Any]) -> List[Session]:
    """One weekend's sessions, in order."""
    out = []
    for name, minutes in LENGTH.items():
        start = _when(race if name == "race" else race.get(name) or {})
        if start:
            out.append((f"{race.get('raceName')} {name}", start, start + timedelta(minutes=minutes)))
    return sorted(out, key=lambda s: s[1])


def weekend(now: datetime, calendar: List[Dict[str, Any]]) -> Optional[Tuple[datetime, datetime]]:
    """(from, to) of the race weekend under way now, or None."""
    for race in calendar:
        ss = sessions(race)
        if ss and ss[0][1] - BEFORE_WEEKEND <= now <= ss[-1][2] + WATCH:
            return ss[0][1] - BEFORE_WEEKEND, ss[-1][2] + WATCH
    return None


def watching(now: datetime, calendar: List[Dict[str, Any]]) -> Optional[str]:
    """The session whose end is being watched now (within WATCH after it), or None."""
    for race in calendar:
        for label, _, end in sessions(race):
            if end <= now <= end + WATCH:
                return label
    return None


def decide(now: datetime, calendar: Optional[List[Dict[str, Any]]],
           last_update: Callable[[], Optional[datetime]]) -> Dict[str, Any]:
    """{run, results_refresh, until, reason}. `last_update` is only asked on a normal day."""
    span = weekend(now, calendar or [])
    if span:
        until = min(span[1], now + MAX_RUN)
        return {"run": True, "results_refresh": False, "until": until,
                "reason": f"a race weekend: watching each session's end until {until:%a %H:%M} UTC"}
    last = last_update()
    if last is not None and now - last < MIN_GAP:
        return {"run": False, "results_refresh": False, "until": None,
                "reason": f"updated {int((now - last).total_seconds() // 60)} minutes ago"}
    return {"run": True, "results_refresh": True, "until": None,
            "reason": "no update yet" if last is None else f"last update {now - last} ago"}


def _get(url: str, token: Optional[str] = None) -> Any:
    request = urllib.request.Request(url, headers={"Accept": "application/json",
                                                   **({"Authorization": f"Bearer {token}"} if token else {})})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def fetch_calendar() -> Optional[List[Dict[str, Any]]]:
    try:
        return _get(CALENDAR_URL)["MRData"]["RaceTable"]["Races"]
    except Exception as exc:                         # noqa: BLE001 — any failure: update once anyway
        print(f"couldn't read the calendar: {exc}", file=sys.stderr)
        return None


def last_update_from(runs: List[Dict[str, Any]], jobs_of: Callable[[int], List[Dict[str, Any]]]) -> Optional[datetime]:
    """When the update step last finished successfully, newest run first."""
    for run in runs:
        for job in jobs_of(run["id"]):
            for step in job.get("steps") or []:
                if step.get("name") == UPDATE_STEP and step.get("conclusion") == "success" and step.get("completed_at"):
                    return datetime.fromisoformat(step["completed_at"].replace("Z", "+00:00"))
    return None


def fetch_last_update() -> Optional[datetime]:
    repo, token = os.getenv("GITHUB_REPOSITORY"), os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")
    if not repo or not token:
        return None
    api = f"https://api.github.com/repos/{repo}/actions"
    try:
        runs = _get(f"{api}/workflows/{WORKFLOW}/runs?status=completed&per_page=30", token)["workflow_runs"]
        return last_update_from(runs, lambda run_id: _get(f"{api}/runs/{run_id}/jobs", token)["jobs"])
    except Exception as exc:                         # noqa: BLE001 — unknown: update
        print(f"couldn't read the previous runs: {exc}", file=sys.stderr)
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--still-weekend", action="store_true", help="exit 0 if a race weekend is still under way")
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    calendar = fetch_calendar()
    if args.still_weekend:
        span = weekend(now, calendar or [])
        print(f"Race weekend {'under way until ' + format(span[1], '%a %H:%M UTC') if span else 'over'}.", file=sys.stderr)
        return 0 if span else 1
    plan = decide(now, calendar, fetch_last_update)
    print(f"{'Running' if plan['run'] else 'Skipping'} data upkeep: {plan['reason']}.", file=sys.stderr)
    print(f"run={'true' if plan['run'] else 'false'}")
    print(f"results_refresh={'true' if plan['results_refresh'] else 'false'}")
    print(f"until={plan['until'].isoformat() if plan['until'] else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
