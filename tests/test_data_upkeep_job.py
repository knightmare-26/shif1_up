"""The scheduled data upkeep (scripts/data_upkeep_job.py) stores new data straight into Supabase while
the API sleeps; the API picks it up when it next starts — or, if it was awake meanwhile, at its next
pass, from the marker the job leaves (its own pass found nothing new to fetch). Services are faked."""
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import main

pytestmark = pytest.mark.asyncio

spec = importlib.util.spec_from_file_location("data_upkeep_job", Path(__file__).parent.parent / "scripts" / "data_upkeep_job.py")
job = importlib.util.module_from_spec(spec)
spec.loader.exec_module(job)


class CacheDb:
    def __init__(self):
        self.cache = {}

    async def get_prediction_cache(self, circuit, session):
        return self.cache.get((circuit, session))

    async def set_prediction_cache(self, circuit, session, trained_at, result):
        self.cache[(circuit, session)] = {"model_trained_at": trained_at, "result": result}
        return True


def iso(minutes_from_now):
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes_from_now)).isoformat()


async def test_an_awake_api_retrains_on_data_the_job_stored_after_its_training(monkeypatch):
    db = CacheDb()
    monkeypatch.setattr(main, "duckdb_service", db)
    monkeypatch.setattr(main.prediction_service, "data_read_at", iso(-30))
    assert await main._stored_since_training() is False                # nothing stored by the job yet

    await main._mark_data_stored(["2026_Singapore sprint", "2026_Singapore qualifying"])
    assert await main._stored_since_training() is True

    monkeypatch.setattr(main.prediction_service, "data_read_at", iso(1))   # retrained since
    assert await main._stored_since_training() is False


async def test_a_database_without_the_marker_doesnt_force_a_retrain(monkeypatch):
    class Broken:
        async def get_prediction_cache(self, *args):
            raise RuntimeError("no such table")
    monkeypatch.setattr(main, "duckdb_service", Broken())
    assert await main._stored_since_training() is False


@pytest.fixture
def job_main(monkeypatch):
    calls = []
    db = CacheDb()

    async def connect():
        calls.append("connect")
        monkeypatch.setattr(main, "duckdb_service", db)

    async def disconnect():
        calls.append("disconnect")

    stored = [["2026_Singapore sprint"]]               # what each pass stores, then nothing

    async def upkeep_pass():
        calls.append("upkeep")
        return (stored.pop(0) if stored else []), []

    async def refresh(database, days):
        calls.append("results refresh")
        return [{"race_id": "2026_Bahrain", "session_type": "race"}]

    async def train(database):
        calls.append("train")

    async def keep_backtest_current():
        calls.append("backtest")

    monkeypatch.setattr(main, "DATABASE_URL", "postgresql://example")
    monkeypatch.setattr(main, "_connect_database", connect)
    monkeypatch.setattr(main, "_disconnect_database", disconnect)
    monkeypatch.setattr(main, "_data_upkeep_pass", upkeep_pass)
    monkeypatch.setattr(main.ingest_service, "refresh_recent_results", refresh)
    monkeypatch.setattr(main.prediction_service, "train", train)
    monkeypatch.setattr(main, "_keep_backtest_current", keep_backtest_current)
    monkeypatch.setattr(main, "_walkforward_job", None)
    monkeypatch.setattr(main.prediction_service, "clear_cache_after_training", True)
    monkeypatch.setattr(main.prediction_service, "data_read_at", None)
    return calls, db


async def test_the_job_stores_marks_and_rebuilds_predicted_vs_actual(job_main):
    calls, db = job_main
    assert await job.run(results_refresh=True) == 0

    assert calls == ["connect", "upkeep", "results refresh", "train", "backtest", "disconnect"]
    marker = db.cache[(main.UPKEEP_MARKER, "stored")]["result"]
    assert marker["what"] == ["2026_Singapore sprint", "2026_Bahrain race (corrected)"]
    # Its own models include it (no retrain at its next pass), and the site's cached predictions are
    # left to the API, which clears them when it retrains on the new data.
    assert main.prediction_service.data_read_at == marker["at"]
    assert main.prediction_service.clear_cache_after_training is False


async def test_without_the_database_secret_the_job_says_so(job_main, monkeypatch):
    calls, _ = job_main
    monkeypatch.setattr(main, "DATABASE_URL", None)
    assert await job.run() == 1
    assert calls == []


AUSTIN = {"raceName": "United States Grand Prix", "date": "2026-10-25", "time": "20:00:00Z",
          "FirstPractice": {"date": "2026-10-23", "time": "17:30:00Z"},
          "SecondPractice": {"date": "2026-10-23", "time": "21:00:00Z"}}


async def test_over_a_race_weekend_it_stays_on_checking_every_15_minutes_after_a_session_ends(job_main, monkeypatch):
    """Friday at Austin: started at 16:10 (before FP1), on until 21:50 — a pass at the start, then one
    every 15 minutes from FP1's end (18:30) for 2.5 hours; waiting while FP1 and FP2 run."""
    calls, db = job_main
    clock = {"now": datetime(2026, 10, 23, 16, 10, tzinfo=timezone.utc)}
    slept = []

    async def sleep(seconds):
        slept.append(seconds)
        clock["now"] += timedelta(seconds=seconds)

    monkeypatch.setattr(job, "_now", lambda: clock["now"])
    monkeypatch.setattr(job, "_sleep", sleep)
    until = datetime(2026, 10, 23, 21, 50, tzinfo=timezone.utc)
    assert await job.run(until=until, calendar=[AUSTIN]) == 0

    passes = calls.count("upkeep")
    assert passes == 1 + 10                     # the start, then 18:40 ... 20:55 (FP1's watch, 15-minute steps)
    assert set(slept) == {900.0} and clock["now"] < until
    assert calls[-1] == "disconnect"
    assert db.cache[(main.UPKEEP_MARKER, "stored")]["result"]["what"] == ["2026_Singapore sprint"]   # marked straight away
