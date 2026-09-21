"""Prediction training: single-flight, off the event loop, and swapped in atomically.

These guard three real problems seen on Render's free tier:
  * three parallel /predict calls on a cold server each started their own training;
  * training ran on the event loop, so /health stalled for the whole duration;
  * a retrain mutated live state step by step while requests were reading it.
"""
import asyncio
import time

import pandas as pd
import pytest

from services.prediction_service import PredictionService

pytestmark = pytest.mark.asyncio


class FakeDb:
    def __init__(self):
        self.cache_cleared = 0

    async def clear_prediction_cache(self):
        self.cache_cleared += 1


def service(monkeypatch, fit_seconds=0.0, load_delay=0.0):
    """A PredictionService whose data load and fit are fakes, so no ML libraries or DB are needed."""
    svc = PredictionService(model_dir="unused")
    calls = {"load": 0, "fit": 0}

    async def fake_load(_db):
        calls["load"] += 1
        await asyncio.sleep(load_delay)
        return pd.DataFrame({"x": range(50)})

    def fake_fit(self, raw, xgb, lgb):
        calls["fit"] += 1
        time.sleep(fit_seconds)              # CPU-bound stand-in: blocks the thread it runs in
        self._trained = True
        self._df = pd.DataFrame({"circuit_name": ["Monza"], "year": [2026]})   # what training_status() reads
        self._meta = {"trained_at": "now", "rows": len(raw)}
        return {"rows": len(raw)}

    monkeypatch.setattr(svc, "_load_raw", fake_load)
    monkeypatch.setattr(PredictionService, "_fit", fake_fit)
    monkeypatch.setattr(PredictionService, "load_from_disk", lambda self: False)
    return svc, calls


async def test_parallel_predictions_on_a_cold_server_share_one_training(monkeypatch):
    svc, calls = service(monkeypatch, fit_seconds=0.05, load_delay=0.05)
    db = FakeDb()

    # qualifying, race and sprint predictions all arrive together
    await asyncio.gather(*[svc._ensure_trained(db) for _ in range(3)])

    assert calls["fit"] == 1
    assert svc._trained is True and svc._meta["rows"] == 50


async def test_a_second_caller_waits_and_does_not_retrain_once_the_first_finishes(monkeypatch):
    svc, calls = service(monkeypatch, fit_seconds=0.05)
    db = FakeDb()

    first = asyncio.create_task(svc._ensure_trained(db))
    await asyncio.sleep(0.01)
    assert svc.training_status()["training"] is True          # visible to /predict/status
    await svc._ensure_trained(db)                             # waits for the first
    await first

    assert calls["fit"] == 1
    assert svc.training_status()["training"] is False


async def test_an_explicit_retrain_is_serialised_with_a_running_training(monkeypatch):
    svc, calls = service(monkeypatch, fit_seconds=0.05, load_delay=0.05)
    db = FakeDb()

    startup = asyncio.create_task(svc._ensure_trained(db))
    await asyncio.sleep(0.01)
    retrain = await svc.train(db)                             # e.g. after an ingest, while warming up

    await startup
    assert retrain["success"] is True
    assert calls["fit"] == 2                                  # one after the other, never overlapping
    assert db.cache_cleared == 2


async def test_the_event_loop_stays_responsive_while_fitting(monkeypatch):
    svc, _ = service(monkeypatch, fit_seconds=0.6)            # blocks its thread for 0.6s
    ticks = []

    async def ticker():
        while True:
            ticks.append(time.monotonic())
            await asyncio.sleep(0.02)

    t = asyncio.create_task(ticker())
    await svc.train(FakeDb())
    t.cancel()

    # If fitting ran on the loop, the ticker would have been frozen for the whole 0.6s.
    gaps = [b - a for a, b in zip(ticks, ticks[1:])]
    assert len(ticks) > 15
    assert max(gaps) < 0.3


async def test_fitting_happens_on_a_private_copy_and_is_swapped_in_atomically(monkeypatch):
    svc, _ = service(monkeypatch)
    svc._trained, svc._df, svc._meta = True, pd.DataFrame({"old": [1]}), {"trained_at": "before"}
    seen_during_fit = {}

    def spying_fit(self, raw, xgb, lgb):
        seen_during_fit["is_copy"] = self is not svc
        seen_during_fit["live_meta_untouched"] = svc._meta == {"trained_at": "before"}
        self._meta = {"trained_at": "after"}
        self._trained = True
        self._df = pd.DataFrame({"new": [1]})
        return {"rows": 1}

    monkeypatch.setattr(PredictionService, "_fit", spying_fit)
    await svc.train(FakeDb())

    assert seen_during_fit == {"is_copy": True, "live_meta_untouched": True}
    assert svc._meta == {"trained_at": "after"} and list(svc._df.columns) == ["new"]


async def test_a_model_that_is_skipped_keeps_the_previous_one(monkeypatch):
    svc, _ = service(monkeypatch)
    svc._quali_model = "previous quali model"

    def fit_without_quali(self, raw, xgb, lgb):     # e.g. grid column NULL this time: quali is skipped
        self._trained, self._df, self._meta = True, pd.DataFrame({"a": [1]}), {}
        return {}

    monkeypatch.setattr(PredictionService, "_fit", fit_without_quali)
    await svc.train(FakeDb())

    assert svc._quali_model == "previous quali model"   # same behaviour as before the refactor


async def test_insufficient_data_reports_failure_and_leaves_state_alone(monkeypatch):
    svc, calls = service(monkeypatch)

    async def tiny(_db):
        return pd.DataFrame({"x": range(3)})

    monkeypatch.setattr(svc, "_load_raw", tiny)
    result = await svc.train(FakeDb())

    assert result["success"] is False and "Insufficient" in result["error"]
    assert calls["fit"] == 0 and svc._trained is False
