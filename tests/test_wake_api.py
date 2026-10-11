"""scripts/wake_api.py: when the API is woken so its data upkeep runs without a visitor."""
import importlib.util
from datetime import datetime, timezone
from pathlib import Path

spec = importlib.util.spec_from_file_location("wake_api", Path(__file__).parent.parent / "scripts" / "wake_api.py")
wake_api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wake_api)

# Jolpica's calendar entry for Singapore 2026 (a sprint weekend), as served.
SINGAPORE = {"raceName": "Singapore Grand Prix", "date": "2026-10-11", "time": "12:00:00Z",
             "FirstPractice": {"date": "2026-10-09", "time": "08:30:00Z"},
             "SprintQualifying": {"date": "2026-10-09", "time": "12:30:00Z"},
             "Sprint": {"date": "2026-10-10", "time": "09:00:00Z"},
             "Qualifying": {"date": "2026-10-10", "time": "13:00:00Z"}}
OLD = {"raceName": "Old Grand Prix", "date": "1950-05-13"}            # no times: no windows


def at(text):
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


def test_awake_through_each_session_and_the_hours_after():
    calendar = [SINGAPORE, OLD]
    assert wake_api.wake_reason(at("2026-10-10T09:20"), calendar) == "Singapore Grand Prix Sprint"
    # Saturday evening: qualifying ended ~14:00 — the window runs until 17:00, so it's stored (the
    # server slept through exactly this before).
    assert wake_api.wake_reason(at("2026-10-10T16:50"), calendar) == "Singapore Grand Prix Qualifying"
    assert wake_api.wake_reason(at("2026-10-11T17:50"), calendar) == "Singapore Grand Prix race"


def test_otherwise_only_the_6_hourly_upkeep():
    calendar = [SINGAPORE]
    assert wake_api.wake_reason(at("2026-10-10T19:30"), calendar) is None
    assert wake_api.wake_reason(at("2026-10-14T09:30"), calendar) is None
    assert wake_api.wake_reason(at("2026-10-14T06:44"), calendar) == "the 6-hourly data upkeep"
    assert wake_api.wake_reason(at("2026-10-14T18:04"), calendar) == "the 6-hourly data upkeep"


def test_no_calendar_wakes_anyway():
    assert wake_api.wake_reason(at("2026-10-14T09:30"), None) == "the calendar couldn't be read"


def test_awake_hours_stay_well_inside_the_free_750_a_month():
    """A month with two sprint weekends: windows plus the upkeep hours, counted in 10-minute runs
    (each keeps the server up ~15 minutes, so a run counts as 10 minutes awake)."""
    from datetime import timedelta
    second = {"raceName": "Second Grand Prix", "date": "2026-10-25", "time": "19:00:00Z",
              "FirstPractice": {"date": "2026-10-23", "time": "17:30:00Z"},
              "SprintQualifying": {"date": "2026-10-23", "time": "21:30:00Z"},
              "Sprint": {"date": "2026-10-24", "time": "17:00:00Z"},
              "Qualifying": {"date": "2026-10-24", "time": "21:00:00Z"}}
    awake, t = 0, at("2026-10-01T00:04")
    while t < at("2026-11-01T00:00"):
        awake += wake_api.wake_reason(t, [SINGAPORE, second]) is not None
        t += timedelta(minutes=10)
    hours = awake * 10 / 60 + 0.25 * 4 * 31          # plus each stretch's last 15 minutes
    assert hours < 250
