"""Phase 1 (#30): practice pace as gaps, neutral values where a weekend has no practice, and the
coming weekend's stored practice used when its race is predicted."""
import os
import numpy as np
import pandas as pd
import pytest

from services.practice_features import COLUMNS, GAP_CAP, practice_features
from services.prediction_service import PredictionService
from tests.test_prediction_training import FakeLgb, synthetic_raw


def lap(seconds: float) -> str:
    return str(pd.Timedelta(seconds=seconds))       # stored like "0 days 00:01:30.000000"


def session(race_id, session_type, laps, teams):
    return [{"race_id": race_id, "session_type": session_type, "driver_id": d, "constructor_id": teams.get(d, ""),
             "position": i + 1, "time": lap(t) if t else ""}
            for i, (d, t) in enumerate(sorted(laps.items(), key=lambda kv: kv[1] or 1e9))]


TEAMS = {"aaa": "fast", "bbb": "fast", "ccc": "slow", "ddd": "slow"}


def test_gaps_to_the_fastest_car_the_team_and_the_teammate():
    raw = pd.DataFrame(session("r1", "fp1", {"aaa": 90.0, "bbb": 90.9, "ccc": 91.8, "ddd": 92.7}, TEAMS)
                       + session("r1", "fp2", {"aaa": 89.1, "bbb": 89.0, "ccc": 90.0, "ddd": 95.0}, TEAMS))
    f = practice_features(raw).set_index("driver_id")

    assert f.loc["aaa", "driver_practice_best_rank"] == 1
    assert f.loc["aaa", "driver_practice_gap_pct"] == pytest.approx(0.0)                 # fastest in FP1
    assert f.loc["bbb", "driver_practice_gap_pct"] == pytest.approx(0.0)                 # fastest in FP2
    assert f.loc["ccc", "driver_practice_gap_pct"] == pytest.approx(100 * (90.0 / 89.0 - 1))
    assert f.loc["ccc", "team_practice_gap_pct"] == f.loc["ddd", "team_practice_gap_pct"]
    # ccc vs ddd: -1% in FP1, -5.6% in FP2 -> median
    assert f.loc["ccc", "driver_practice_teammate_gap_pct"] < 0 < f.loc["ddd", "driver_practice_teammate_gap_pct"]


def test_a_lap_far_off_the_pace_is_capped_and_a_missing_time_is_no_gap():
    raw = pd.DataFrame(session("r1", "fp1", {"aaa": 90.0, "bbb": 120.0, "ccc": None}, TEAMS))
    f = practice_features(raw).set_index("driver_id")

    assert f.loc["bbb", "driver_practice_gap_pct"] == GAP_CAP
    assert np.isnan(f.loc["ccc", "driver_practice_gap_pct"]) and f.loc["ccc", "driver_practice_best_rank"] == 3


def test_teams_come_from_the_weekends_race_rows_when_practice_lacks_them():
    rows = session("r1", "fp1", {"aaa": 90.0, "bbb": 91.0, "ccc": 92.0}, {})            # no teams in practice
    rows += [{"race_id": "r1", "session_type": "race", "driver_id": d, "constructor_id": TEAMS[d], "position": i + 1, "time": ""}
             for i, d in enumerate(["aaa", "bbb", "ccc"])]
    f = practice_features(pd.DataFrame(rows)).set_index("driver_id")

    assert f.loc["bbb", "team_practice_gap_pct"] == pytest.approx(0.0)                  # aaa's team-mate


# --- in the model ------------------------------------------------------------------------------

DRIVERS = tuple(f"d{i}" for i in range(1, 13))


def history_with_practice(upcoming_practice=True):
    raw = synthetic_raw(years=[2024], rounds_per_year=4, drivers=DRIVERS)
    rows = []
    rounds = (1, 2, 3, 4, 5) if upcoming_practice else (1, 2, 3, 4)
    for rnd in rounds:
        for i, d in enumerate(DRIVERS):
            rows.append({"race_id": f"2024_{rnd}", "driver_id": d, "constructor_id": f"c{i % 2}", "position": i + 1,
                         "grid": None, "points": 0.0, "status": "", "session_type": "fp2", "time": lap(90 + i * 0.3),
                         "circuit_name": f"circuit{rnd}", "year": 2024, "round": rnd, "race_name": f"GP{rnd}",
                         "driver_name": d, "constructor_name": f"Team {i % 2}"})
    return pd.concat([raw, pd.DataFrame(rows)], ignore_index=True)       # round 5: practice only, race to come


def test_the_coming_weekends_practice_is_used_for_its_prediction():
    svc = PredictionService(model_dir=os.environ["MODEL_DIR"])
    svc._fit(history_with_practice(), FakeLgb())

    rows = svc._build_prediction_rows("circuit5").set_index("driver_id")
    assert svc.weekend_practice("circuit5") is not None
    assert rows.loc["d1", "driver_practice_best_rank"] == 1 and rows.loc["d12", "driver_practice_best_rank"] == 12
    assert rows.loc["d1", "driver_practice_gap_pct"] == pytest.approx(0.0)


def test_without_practice_every_driver_gets_the_neutral_median():
    svc = PredictionService(model_dir=os.environ["MODEL_DIR"])
    svc._fit(history_with_practice(upcoming_practice=False), FakeLgb())

    rows = svc._build_prediction_rows("circuit2")          # a past circuit; nothing stored for a new weekend
    assert svc.weekend_practice("circuit2") is None
    for col in COLUMNS:
        if col in svc._practice_medians:
            assert rows[col].nunique() == 1 and rows[col].iloc[0] == svc._practice_medians[col]
    assert svc._practice_medians["driver_practice_best_rank"] != 10       # not the old fill-in


@pytest.mark.asyncio
async def test_a_prediction_says_whether_it_used_this_weekends_practice():
    class Db:
        async def get_prediction_cache(self, *a):
            return None

        async def set_prediction_cache(self, *a):
            pass

    svc = PredictionService(model_dir=os.environ["MODEL_DIR"])
    svc._fit(history_with_practice(), FakeLgb())
    svc._df = svc._df          # trained; _ensure_trained is a no-op

    assert (await svc.predict_qualifying("circuit5", Db()))["practice_used"] is True
    assert (await svc.predict_qualifying("circuit2", Db()))["practice_used"] is False


@pytest.mark.asyncio
async def test_a_race_predicted_after_qualifying_starts_from_the_real_qualifying_order():
    class Db:
        async def get_prediction_cache(self, *a):
            return None

        async def set_prediction_cache(self, *a):
            pass

    raw = history_with_practice()
    quali = [{"race_id": "2024_5", "driver_id": d, "constructor_id": f"c{i % 2}", "position": len(DRIVERS) - i,
              "grid": None, "points": 0.0, "status": "", "session_type": "qualifying", "time": "",
              "circuit_name": "circuit5", "year": 2024, "round": 5, "race_name": "GP5", "driver_name": d,
              "constructor_name": f"Team {i % 2}"} for i, d in enumerate(DRIVERS)]          # d12 on pole
    svc = PredictionService(model_dir=os.environ["MODEL_DIR"])
    svc._fit(pd.concat([raw, pd.DataFrame(quali)], ignore_index=True), FakeLgb())

    race = await svc.predict_race("circuit5", Db())
    assert race["grid_source"] == "this weekend's qualifying"
    assert {p["driver_id"]: p["predicted_grid"] for p in race["predictions"]}["d12"] == 1
    assert (await svc.predict_race("circuit2", Db()))["grid_source"] == "predicted qualifying"


@pytest.mark.asyncio
async def test_a_sprint_prediction_carries_its_scores_for_the_odds():
    class Db:
        async def get_prediction_cache(self, *a):
            return None

        async def set_prediction_cache(self, *a):
            pass

    raw = history_with_practice()
    sprint = raw[(raw["session_type"] == "race") & (raw["round"] <= 4)].assign(session_type="sprint")
    svc = PredictionService(model_dir=os.environ["MODEL_DIR"])
    svc._fit(pd.concat([raw, sprint], ignore_index=True), FakeLgb())
    out = await svc.predict_sprint("circuit5", Db())
    assert out["success"] and all("score" in p and "dnf_rate" in p for p in out["predictions"])
