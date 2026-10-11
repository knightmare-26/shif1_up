"""scripts/upkeep_schedule.py: when the scheduled data upkeep runs (GitHub Actions, straight into
Supabase, so the sleeping API is never woken)."""
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

spec = importlib.util.spec_from_file_location("upkeep_schedule", Path(__file__).parent.parent / "scripts" / "upkeep_schedule.py")
schedule = importlib.util.module_from_spec(spec)
spec.loader.exec_module(schedule)

# Jolpica's calendar entry for Singapore 2026 (a sprint weekend), as served.
SINGAPORE = {"raceName": "Singapore Grand Prix", "date": "2026-10-11", "time": "12:00:00Z",
             "FirstPractice": {"date": "2026-10-09", "time": "08:30:00Z"},
             "SprintQualifying": {"date": "2026-10-09", "time": "12:30:00Z"},
             "Sprint": {"date": "2026-10-10", "time": "09:00:00Z"},
             "Qualifying": {"date": "2026-10-10", "time": "13:00:00Z"}}
OLD = {"raceName": "Old Grand Prix", "date": "1950-05-13"}            # no times: no windows


def at(text):
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


def test_runs_through_each_session_and_the_hours_after():
    calendar = [SINGAPORE, OLD]
    assert schedule.decide(at("2026-10-10T09:20"), calendar) == (True, False, "Singapore Grand Prix Sprint")
    # Saturday evening: qualifying ended ~14:00 and the server slept through it — the job doesn't need it.
    assert schedule.decide(at("2026-10-10T16:50"), calendar) == (True, False, "Singapore Grand Prix Qualifying")
    assert schedule.decide(at("2026-10-11T17:50"), calendar) == (True, False, "Singapore Grand Prix race")


def test_otherwise_the_6_hourly_upkeep_with_the_results_refresh():
    calendar = [SINGAPORE]
    assert schedule.decide(at("2026-10-10T19:37"), calendar)[0] is False
    assert schedule.decide(at("2026-10-14T09:37"), calendar)[0] is False
    assert schedule.decide(at("2026-10-14T06:07"), calendar) == (True, True, "the 6-hourly data upkeep")
    assert schedule.decide(at("2026-10-14T18:22"), calendar)[:2] == (True, True)
    assert schedule.decide(at("2026-10-14T18:37"), calendar)[0] is False        # once is enough


def test_no_calendar_runs_anyway():
    assert schedule.decide(at("2026-10-14T09:37"), None) == (True, False, "the calendar couldn't be read")


def test_a_month_of_runs_stays_modest():
    """Runs with something to do in a month with two sprint weekends (every 15 minutes)."""
    second = {"raceName": "Second Grand Prix", "date": "2026-10-25", "time": "19:00:00Z",
              "FirstPractice": {"date": "2026-10-23", "time": "17:30:00Z"},
              "SprintQualifying": {"date": "2026-10-23", "time": "21:30:00Z"},
              "Sprint": {"date": "2026-10-24", "time": "17:00:00Z"},
              "Qualifying": {"date": "2026-10-24", "time": "21:00:00Z"}}
    runs, t = 0, at("2026-10-01T00:07")
    while t < at("2026-11-01T00:00"):
        runs += schedule.decide(t, [SINGAPORE, second])[0]
        t += timedelta(minutes=15)
    assert runs < 500                      # ~250 for the 6-hourly upkeep, ~90 per sprint weekend
