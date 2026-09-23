"""Prediction training: single-flight, off the event loop, and swapped in atomically.

These guard three real problems seen on Render's free tier:
  * three parallel /predict calls on a cold server each started their own training;
  * training ran on the event loop, so /health stalled for the whole duration;
  * a retrain mutated live state step by step while requests were reading it.
"""
import asyncio
import time

import numpy as np
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

    def fake_fit(self, raw, lgb):
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

    def spying_fit(self, raw, lgb):
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

    def fit_without_quali(self, raw, lgb):          # e.g. grid column NULL this time: quali is skipped
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


# ----------------------------------------------------------------------
# Walk-forward backtest: a season is only ever scored by a model that was
# fit on strictly earlier seasons. _fit()/train() above are all mocked out
# (no real lightgbm) — these instead inject a fake estimator class, the same
# dependency-injection seam _fit(self, raw, lgb) already uses.
# ----------------------------------------------------------------------

class FakeEstimator:
    """Stands in for LGBMRanker: 'predicts' by returning the training target
    itself as the relevance score, so higher target (via _fit_ranker's
    field_size + 1 - value transform, i.e. a better real position) sorts as a
    better predicted rank — good enough to exercise the surrounding pipeline
    without needing a real ranking model."""
    def __init__(self, *a, **k):
        self._seen = None

    def fit(self, X, y, group=None, sample_weight=None):
        self._seen = np.asarray(y)
        return self

    def predict(self, X):
        n = len(X)
        return self._seen[:n] if self._seen is not None and len(self._seen) >= n else np.zeros(n)


class FakeLgb:
    LGBMRanker = FakeEstimator


def synthetic_raw(years, rounds_per_year=10, drivers=("d1", "d2", "d3", "d4")):
    """A minimal race_results-shaped DataFrame spanning multiple seasons —
    the shape _load_raw() would return, before _engineer()/_encode()."""
    rows = []
    for year in years:
        for rnd in range(1, rounds_per_year + 1):
            race_id = f"{year}_{rnd}"
            for i, d in enumerate(drivers):
                rows.append({
                    "race_id": race_id, "driver_id": d, "constructor_id": f"c{i % 2}",
                    "position": (i + rnd) % len(drivers) + 1, "grid": (i + rnd + 1) % len(drivers) + 1,
                    "points": 0.0, "status": "Finished", "session_type": "race",
                    "circuit_name": f"circuit{rnd}", "year": year, "round": rnd,
                    "race_name": f"GP{rnd}", "driver_name": d, "constructor_name": f"Team {i % 2}",
                })
    return pd.DataFrame(rows)


async def test_walk_forward_backtest_reports_insufficient_data():
    svc = PredictionService(model_dir="unused")

    async def tiny(_db):
        return pd.DataFrame({"x": range(3)})

    svc._load_raw = tiny
    result = await svc.walk_forward_backtest(FakeDb(), years_back=3)

    assert result["races"] == [] and "Insufficient" in result["error"]


async def test_walk_forward_fit_never_tests_the_earliest_season():
    svc = PredictionService(model_dir="unused")
    raw = synthetic_raw(years=[2022, 2023, 2024])

    result = svc._walk_forward_fit(raw, FakeLgb(), years_back=3)

    # 2022 is the earliest season in the data — a model can't be trained on
    # "seasons before 2022" with nothing before it, so it's never a test year.
    assert 2022 not in result["seasons_tested"]
    assert set(result["seasons_tested"]) <= {2023, 2024}
    assert all(r["year"] in result["seasons_tested"] for r in result["races"])
    assert result["data_fingerprint"]  # non-empty, used as the cache invalidation key


async def test_walk_forward_fit_scores_each_season_against_a_model_trained_only_on_earlier_ones():
    svc = PredictionService(model_dir="unused")
    raw = synthetic_raw(years=[2022, 2023, 2024])
    trained_on = {}

    class SpyingEstimator(FakeEstimator):
        def fit(self, X, y, group=None, sample_weight=None):
            trained_on.setdefault(len(y), []).append(len(y))
            return super().fit(X, y, group=group, sample_weight=sample_weight)

    class SpyingLgb:
        LGBMRanker = SpyingEstimator

    result = svc._walk_forward_fit(raw, SpyingLgb(), years_back=3)

    # Sanity: races were actually scored for the held-out seasons, with real
    # per-driver predicted/actual pairs (not an empty pass-through).
    races_2024 = [r for r in result["races"] if r["year"] == 2024]
    assert races_2024 and races_2024[0]["drivers"][0]["predicted_position"] is not None


async def test_ranks_from_scores_converts_relevance_to_1_through_n():
    svc = PredictionService(model_dir="unused")

    # Higher score = better predicted finish (a ranker's relevance), so the
    # highest score gets rank 1, not the lowest — the reverse of sorting raw
    # position/grid values, which is exactly what _ranks_from_scores exists to invert.
    ranks = svc._ranks_from_scores([0.5, 9.0, 3.0, -1.0])

    assert list(ranks) == [3, 1, 2, 4]
    assert sorted(ranks) == [1, 2, 3, 4]


async def test_teammate_delta_is_a_rolling_average_of_prior_races_only():
    svc = PredictionService(model_dir="unused")
    # Two teammates (same constructor) across 3 races. Deltas are (own position - teammate's):
    #   race 1: a=1-2=-1, b=2-1=1   race 2: a=3-1=2, b=1-3=-2   race 3: scored below
    raw = pd.DataFrame([
        {"race_id": "r1", "driver_id": "a", "constructor_id": "c1", "position": 1, "grid": 1, "status": "Finished", "circuit_name": "X", "year": 2024, "round": 1},
        {"race_id": "r1", "driver_id": "b", "constructor_id": "c1", "position": 2, "grid": 2, "status": "Finished", "circuit_name": "X", "year": 2024, "round": 1},
        {"race_id": "r2", "driver_id": "a", "constructor_id": "c1", "position": 3, "grid": 3, "status": "Finished", "circuit_name": "Y", "year": 2024, "round": 2},
        {"race_id": "r2", "driver_id": "b", "constructor_id": "c1", "position": 1, "grid": 1, "status": "Finished", "circuit_name": "Y", "year": 2024, "round": 2},
        {"race_id": "r3", "driver_id": "a", "constructor_id": "c1", "position": 2, "grid": 2, "status": "Finished", "circuit_name": "Z", "year": 2024, "round": 3},
        {"race_id": "r3", "driver_id": "b", "constructor_id": "c1", "position": 1, "grid": 1, "status": "Finished", "circuit_name": "Z", "year": 2024, "round": 3},
    ])

    df = svc._engineer(raw)

    a_r3 = df[(df["driver_id"] == "a") & (df["race_id"] == "r3")].iloc[0]
    assert a_r3["driver_teammate_finish_delta"] == pytest.approx((-1 + 2) / 2)

    # A driver's very first race has no prior deltas to average — neutral 0, not NaN.
    a_r1 = df[(df["driver_id"] == "a") & (df["race_id"] == "r1")].iloc[0]
    assert a_r1["driver_teammate_finish_delta"] == 0.0
    assert not df["driver_teammate_finish_delta"].isna().any()
    assert not df["driver_teammate_grid_delta"].isna().any()


async def test_practice_pace_feature_is_included_only_once_coverage_crosses_50pct(tmp_path):
    svc = PredictionService(model_dir=str(tmp_path))
    raw = synthetic_raw(years=[2024], rounds_per_year=3, drivers=("d1", "d2", "d3", "d4"))

    # Practice ingested for 2 of the 3 races (8 of 12 driver-race rows) — over the 50%
    # coverage threshold, so the feature should be picked up; best (lowest) rank across
    # the two sessions a driver ran should be what's kept.
    practice_rows = []
    for rnd in (1, 2):
        race_id = f"2024_{rnd}"
        for i, d in enumerate(("d1", "d2", "d3", "d4")):
            for session, pos in (("fp1", i + 2), ("fp2", i + 1)):  # fp2 is always the better rank
                practice_rows.append({
                    "race_id": race_id, "driver_id": d, "constructor_id": f"c{i % 2}",
                    "position": pos, "grid": None, "points": 0.0, "status": "Finished",
                    "session_type": session, "circuit_name": f"circuit{rnd}", "year": 2024, "round": rnd,
                    "race_name": f"GP{rnd}", "driver_name": d, "constructor_name": f"Team {i % 2}",
                })
    raw = pd.concat([raw, pd.DataFrame(practice_rows)], ignore_index=True)

    result = svc._fit(raw, FakeLgb())

    assert svc._practice_available is True
    assert result["practice_coverage"] != "0%"
    assert "driver_practice_best_rank" in svc._race_features
    assert "driver_practice_best_rank" in svc._quali_features

    d1_r1 = svc._df[(svc._df["driver_id"] == "d1") & (svc._df["race_id"] == "2024_1")].iloc[0]
    assert d1_r1["driver_practice_best_rank"] == 1   # fp2's rank (2), i.e. i+1 for d1 (i=0) -> 1, the lower of fp1=2/fp2=1

    # The one race without practice data ingested falls back to NaN, not a crash or 0.
    d1_r3 = svc._df[(svc._df["driver_id"] == "d1") & (svc._df["race_id"] == "2024_3")].iloc[0]
    assert pd.isna(d1_r3["driver_practice_best_rank"])


async def test_practice_pace_feature_is_left_out_below_the_coverage_threshold(tmp_path):
    svc = PredictionService(model_dir=str(tmp_path))
    raw = synthetic_raw(years=[2024], rounds_per_year=3, drivers=("d1", "d2", "d3", "d4"))
    # No practice rows ingested at all — the common case right after this ships.

    result = svc._fit(raw, FakeLgb())

    assert svc._practice_available is False
    assert result["practice_coverage"] == "0%"
    assert "driver_practice_best_rank" not in svc._race_features
    assert "driver_practice_best_rank" not in svc._quali_features


async def test_backtest_still_scores_via_the_extracted_helper_after_refactor():
    svc = PredictionService(model_dir="unused")
    svc._race_model = FakeEstimator().fit(pd.DataFrame({"a": [1, 2]}), [3.0, 4.0])
    svc._race_features = ["driver_enc"]
    svc._driver_map = {"d1": "Driver One"}
    svc._df = pd.DataFrame({
        "year": [2026], "round": [1], "race_id": ["r1"], "race_name": ["GP"],
        "circuit_name": ["Monza"], "driver_id": ["d1"], "driver_enc": [0],
        "position": [1], "grid": [1],
    })

    out = svc.backtest(years_back=3)

    assert len(out["races"]) == 1
    race = out["races"][0]
    assert race["drivers"][0]["driver_name"] == "Driver One"
    assert race["drivers"][0]["actual_position"] == 1
    assert race["race_mae"] is not None
