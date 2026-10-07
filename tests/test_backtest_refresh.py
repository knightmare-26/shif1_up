"""Predicted vs Actual keeps up with the season: the walk-forward backtest rebuilds by itself once
the models have been trained on race results it doesn't cover (it used to stay at whatever an admin
last computed — Baku and the Kuala Lumpur round of 2026 never appeared)."""
import asyncio

import pandas as pd
import pytest

import main
from services.prediction_service import PredictionService

pytestmark = pytest.mark.asyncio


def races(n, year=2026):
    return pd.DataFrame({"session_type": ["race"] * n + ["fp1"] * 3, "year": [year] * (n + 3)})


async def test_the_fingerprint_changes_when_a_race_is_added_not_when_practice_is():
    fp = PredictionService.data_fingerprint
    assert fp(races(40)) == "40:2026"
    assert fp(races(60)) != fp(races(40))
    assert fp(pd.concat([races(40), races(0)])) == fp(races(40))     # extra practice rows only


def trained_service(monkeypatch, success=True):
    svc = PredictionService(model_dir="unused")

    async def fake_load(_db):
        return pd.DataFrame({"x": range(50)})

    def fake_fit(self, raw, lgb):
        if not success:
            raise RuntimeError("boom")
        self._trained, self._df, self._meta = True, pd.DataFrame({"year": [2026]}), {"trained_at": "t"}
        return {"rows": len(raw)}

    class Db:
        async def clear_prediction_cache(self):
            pass

    monkeypatch.setattr(svc, "_load_raw", fake_load)
    monkeypatch.setattr(PredictionService, "_fit", fake_fit)
    monkeypatch.setattr(PredictionService, "load_from_disk", lambda self: False)
    return svc, Db()


@pytest.mark.parametrize("success", [True, False])
async def test_a_training_run_tells_the_app_only_when_it_succeeded(monkeypatch, success):
    svc, db = trained_service(monkeypatch, success)
    fired = []

    async def hook():
        fired.append(1)

    svc.on_trained = hook
    await svc._ensure_trained(db)          # cold start
    await svc.train(db)                    # a later retrain (results refresh, ingest)
    await asyncio.sleep(0)

    assert fired == ([1, 1] if success else [])


VERSION = PredictionService.WALK_FORWARD_VERSION


class CacheDb:
    def __init__(self, cached_fingerprint, version=VERSION):
        self.cached = cached_fingerprint and {
            "model_trained_at": cached_fingerprint,
            "result": {"races": [{"race_id": "2026_Spanish"}], "data_fingerprint": cached_fingerprint,
                       "method_version": version},
        }
        self.stored = []

    async def get_prediction_cache(self, circuit, session):
        return self.cached if (circuit, session) == ("_walkforward", "v1") else None

    async def set_prediction_cache(self, circuit, session, key, result):
        self.stored.append((circuit, session, key, result))


@pytest.fixture
def app_state(monkeypatch):
    runs = []

    async def fake_walk_forward(db, years_back=3, previous=None):
        runs.append(previous)
        return {"races": [{"race_id": "2026_Bahrain"}, {"race_id": "2026_Spanish"}], "data_fingerprint": "60:2026",
                "method_version": VERSION}

    def setup(cached_fingerprint, trained_fingerprint="60:2026", version=VERSION):
        db = CacheDb(cached_fingerprint, version)
        monkeypatch.setattr(main, "duckdb_service", db)
        monkeypatch.setattr(main, "_walkforward_job", None)
        monkeypatch.setattr(main.prediction_service, "_meta", {"data_fingerprint": trained_fingerprint})
        monkeypatch.setattr(main.prediction_service, "walk_forward_backtest", fake_walk_forward)
        return db, runs
    return setup


async def test_a_backtest_missing_new_races_is_served_and_rebuilt_in_the_background(app_state):
    db, runs = app_state("40:2026")

    first = await main.predict_backtest()
    assert first["updating"] is True and [r["race_id"] for r in first["races"]] == ["2026_Spanish"]

    await main._walkforward_job
    assert runs == [db.cached["result"]] and db.stored[0][:3] == ("_walkforward", "v1", "60:2026")   # reuses what it can


async def test_an_up_to_date_backtest_is_left_alone(app_state):
    db, runs = app_state("60:2026")

    out = await main.predict_backtest()
    await main._keep_backtest_current()

    assert out["updating"] is False and runs == [] and main._walkforward_job is None


async def test_models_loaded_from_an_older_save_dont_trigger_a_rebuild(app_state):
    db, runs = app_state("40:2026", trained_fingerprint=None)

    assert (await main.predict_backtest())["updating"] is False and runs == []


async def test_training_on_new_results_rebuilds_once_however_often_it_is_asked(app_state):
    db, runs = app_state("40:2026")

    await asyncio.gather(main._keep_backtest_current(), main._keep_backtest_current(), main.predict_backtest())
    await main._walkforward_job

    assert len(runs) == 1


async def test_a_backtest_made_by_an_older_method_is_rebuilt_even_with_the_same_data(app_state):
    db, runs = app_state("60:2026", version="1")

    assert (await main.predict_backtest())["updating"] is True
    await main._walkforward_job
    assert len(runs) == 1
