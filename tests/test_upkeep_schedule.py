"""scripts/upkeep_schedule.py: when the scheduled data upkeep runs (GitHub Actions, straight into
Supabase, so the sleeping API is never woken). GitHub starts only 4-5 of the scheduled runs a day,
at no fixed time, so nothing may depend on a run arriving at a particular time."""
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

spec = importlib.util.spec_from_file_location("upkeep_schedule", Path(__file__).parent.parent / "scripts" / "upkeep_schedule.py")
schedule = importlib.util.module_from_spec(spec)
spec.loader.exec_module(schedule)

# Jolpica's calendar entries, as served: Singapore 2026 (a sprint weekend) and Austin (not).
SINGAPORE = {"raceName": "Singapore Grand Prix", "date": "2026-10-11", "time": "12:00:00Z",
             "FirstPractice": {"date": "2026-10-09", "time": "08:30:00Z"},
             "SprintQualifying": {"date": "2026-10-09", "time": "12:30:00Z"},
             "Sprint": {"date": "2026-10-10", "time": "09:00:00Z"},
             "Qualifying": {"date": "2026-10-10", "time": "13:00:00Z"}}
AUSTIN = {"raceName": "United States Grand Prix", "date": "2026-10-25", "time": "20:00:00Z",
          "FirstPractice": {"date": "2026-10-23", "time": "17:30:00Z"},
          "SecondPractice": {"date": "2026-10-23", "time": "21:00:00Z"},
          "ThirdPractice": {"date": "2026-10-24", "time": "17:30:00Z"},
          "Qualifying": {"date": "2026-10-24", "time": "21:00:00Z"}}
CALENDAR = [SINGAPORE, AUSTIN, {"raceName": "Old Grand Prix", "date": "1950-05-13"}]


def at(text):
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


def never():
    return None


def test_a_normal_day_updates_at_whatever_time_github_starts_the_run():
    """GitHub's real start times on 15 Oct 2026 — none in the old 00/06/12/18 first-half-hour windows,
    so all 23 runs of those five days did nothing."""
    for when in ("2026-10-15T00:57", "2026-10-15T05:46", "2026-10-15T10:22", "2026-10-15T15:18", "2026-10-15T19:21"):
        plan = schedule.decide(at(when), CALENDAR, never)
        assert (plan["run"], plan["results_refresh"], plan["until"]) == (True, True, None), when


def test_but_not_again_within_3_hours_of_the_last_update():
    now = at("2026-10-15T12:00")
    assert schedule.decide(now, CALENDAR, lambda: now - timedelta(hours=1))["run"] is False
    assert schedule.decide(now, CALENDAR, lambda: now - timedelta(hours=3, minutes=5))["run"] is True


def test_a_race_weekend_run_stays_on_and_hands_over_before_githubs_6_hour_limit():
    assert schedule.weekend(at("2026-10-23T16:59"), CALENDAR) is None               # FP1 at 17:30: from 17:00
    plan = schedule.decide(at("2026-10-23T17:10"), CALENDAR, never)                 # Austin, before FP1
    assert (plan["run"], plan["results_refresh"]) == (True, False)
    assert plan["until"] == at("2026-10-23T17:10") + schedule.MAX_RUN
    late = schedule.decide(at("2026-10-25T23:00"), CALENDAR, never)                 # race over at 22:00
    assert late["until"] == at("2026-10-26T00:30")                                  # its watch ends
    assert schedule.weekend(at("2026-10-26T00:31"), CALENDAR) is None               # then a normal day again


def test_every_15_minutes_only_after_a_session_ends():
    assert schedule.watching(at("2026-10-23T18:00"), CALENDAR) is None              # FP1 still running
    assert schedule.watching(at("2026-10-23T18:45"), CALENDAR) == "United States Grand Prix FirstPractice"
    assert schedule.watching(at("2026-10-23T21:15"), CALENDAR) is None              # FP2 running, FP1's watch over
    assert schedule.watching(at("2026-10-24T22:30"), CALENDAR) == "United States Grand Prix Qualifying"
    assert schedule.watching(at("2026-10-25T23:59"), CALENDAR) == "United States Grand Prix race"


def test_no_calendar_still_updates_once():
    assert schedule.decide(at("2026-10-24T22:30"), None, never)["run"] is True


def test_the_last_update_is_the_last_run_whose_update_step_succeeded():
    runs = [{"id": 3}, {"id": 2}, {"id": 1}]
    jobs = {
        3: [{"steps": [{"name": "Anything to pick up now?", "conclusion": "success"},
                       {"name": schedule.UPDATE_STEP, "conclusion": "skipped", "completed_at": "2026-10-16T05:44:00Z"}]}],
        2: [{"steps": [{"name": schedule.UPDATE_STEP, "conclusion": "failure", "completed_at": "2026-10-16T01:00:00Z"}]}],
        1: [{"steps": [{"name": schedule.UPDATE_STEP, "conclusion": "success", "completed_at": "2026-10-15T22:40:00Z"}]}],
    }
    assert schedule.last_update_from(runs, jobs.__getitem__) == at("2026-10-15T22:40")
    assert schedule.last_update_from(runs[:2], jobs.__getitem__) is None
