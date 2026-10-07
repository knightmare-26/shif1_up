"""Phase 0 (#29): the latest season is scored race by race, each round by a model trained only on
what came before it; rebuilds refit only what changed; and the finish odds are scored without
learning from the race being scored (services/backtest_scores.py)."""
import copy

import numpy as np
import pytest

from services import backtest_scores
from services.prediction_service import PredictionService
from tests.test_prediction_training import FakeLgb, synthetic_raw

pytestmark = pytest.mark.asyncio


def spied_service(monkeypatch):
    svc = PredictionService(model_dir="unused")
    fits = []
    original = svc._fit_ranker

    def spy(lgb, train, features, target):
        if target == "position":
            fits.append(max(zip(train["year"], train["round"])))
        return original(lgb, train, features, target)

    monkeypatch.setattr(svc, "_fit_ranker", spy)
    return svc, fits


async def test_the_latest_season_is_scored_round_by_round_by_models_that_never_saw_the_round(monkeypatch):
    svc, fits = spied_service(monkeypatch)
    raw = synthetic_raw(years=[2024, 2025], rounds_per_year=6)

    out = svc._walk_forward_fit(raw, FakeLgb(), years_back=3)

    latest = {r["round"]: r for r in out["races"] if r["year"] == 2025}
    assert latest and all(r["unit"] == f"2025-r{n}" for n, r in latest.items())
    # one model per round of 2025, each trained up to the round before it
    assert fits == [(2024, 6)] + [(2025, n - 1) for n in range(2, 7)]
    assert out["method"]["latest_season"] == 2025 and out["method_version"] == PredictionService.WALK_FORWARD_VERSION


async def test_earlier_seasons_keep_one_model_each():
    raw = synthetic_raw(years=[2023, 2024, 2025], rounds_per_year=6)
    out = PredictionService(model_dir="unused")._walk_forward_fit(raw, FakeLgb(), years_back=3)

    assert {r["unit"] for r in out["races"] if r["year"] == 2024} == {"2024"}


async def test_a_new_race_costs_one_refit_and_leaves_the_others_untouched():
    svc = PredictionService(model_dir="unused")
    full = synthetic_raw(years=[2024, 2025], rounds_per_year=6)
    before = svc._walk_forward_fit(full[~((full["year"] == 2025) & (full["round"] == 6))], FakeLgb(), years_back=3)

    after = svc._walk_forward_fit(full, FakeLgb(), years_back=3, previous=copy.deepcopy(before))

    assert after["refits"] == 1
    unchanged = {r["race_id"]: r["drivers"] for r in before["races"]}
    assert all(r["drivers"] == unchanged[r["race_id"]] for r in after["races"] if r["race_id"] in unchanged)


async def test_a_corrected_result_refits_that_round_and_the_ones_after_it():
    svc = PredictionService(model_dir="unused")
    raw = synthetic_raw(years=[2024, 2025], rounds_per_year=6)
    before = svc._walk_forward_fit(raw, FakeLgb(), years_back=3)

    penalised = raw.copy()
    rows = penalised.index[(penalised["year"] == 2025) & (penalised["round"] == 3)]
    penalised.loc[rows, "position"] = penalised.loc[rows, "position"].to_numpy()[::-1]   # a post-race penalty
    after = svc._walk_forward_fit(penalised, FakeLgb(), years_back=3, previous=copy.deepcopy(before))

    assert after["refits"] == 4            # rounds 3, 4, 5 and 6 of 2025


# --- the odds ---------------------------------------------------------------------------------

def races_for_odds(n=16, seed=1):
    """Sessions where a higher score tends to finish ahead."""
    rng = np.random.default_rng(seed)
    races = []
    for i in range(n):
        scores = np.linspace(2, -2, 10)
        finish = np.argsort(np.argsort(-(scores + rng.normal(0, 1.0, 10)))) + 1
        races.append({"year": 2025, "round": i + 1, "drivers": [
            {"driver_id": f"d{k}", "race_score": float(scores[k]), "actual_position": int(finish[k]),
             "quali_score": float(scores[k]), "actual_grid": int(k + 1)} for k in range(10)]})
    return races


async def test_odds_start_once_there_is_history_and_are_scored_against_baselines():
    races = races_for_odds()
    out = backtest_scores.add_probabilities(races)

    first, later = races[0]["drivers"][0], races[-1]["drivers"][0]
    assert "win_probability" not in first                          # nothing to calibrate on yet
    assert 0 < later["win_probability"] < 1 and "pole_probability" in later
    assert out["races_scored"] == len(races) - backtest_scores.MIN_HISTORY
    win = out["race"]["win"]
    assert win["n"] == 10 * out["races_scored"] and {"uniform", "starting_slot", "reliability"} <= set(win)
    assert win["skill_vs_uniform"] > 0                              # the scores carry real signal


async def test_a_races_odds_never_learn_from_that_race_or_later_ones():
    races = races_for_odds()
    backtest_scores.add_probabilities(races)
    target = races[12]
    chances = [d["win_probability"] for d in target["drivers"]]

    shuffled = copy.deepcopy(races)
    for race in shuffled[12:]:                                      # this race's result and everything after
        for d, pos in zip(race["drivers"], reversed(range(1, 11))):
            d["actual_position"] = pos
    backtest_scores.add_probabilities(shuffled)

    assert [d["win_probability"] for d in shuffled[12]["drivers"]] == chances


async def test_brier_and_log_loss():
    m = backtest_scores._metrics(np.array([1.0, 0.0, 0.5]), np.array([1.0, 0.0, 1.0]))
    assert m["brier"] == pytest.approx(0.25 / 3, abs=1e-4)
    assert m["log_loss"] == pytest.approx(-np.log(0.5) / 3, abs=1e-3)


# --- the predicted order against simple guesses -------------------------------------------------

def race_rows(model, grid, standings, actual):
    return {"year": 2025, "round": 1, "drivers": [
        {"driver_id": f"d{i}", "predicted_position": m, "actual_grid": g, "standings_rank": s, "actual_position": a,
         "predicted_grid": m}
        for i, (m, g, s, a) in enumerate(zip(model, grid, standings, actual))]}


async def test_hit_rates_compare_the_model_with_the_grid_and_the_championship_order():
    n = list(range(1, 11))
    race = race_rows(model=n, grid=[2, 1] + n[2:], standings=n[::-1], actual=n)
    out = backtest_scores.hit_rates([race])["race"]

    assert out["model"]["top1"] == 1.0 and out["model"]["mae"] == 0
    assert out["grid"]["top1"] == 0.0 and out["grid"]["top3"] == 1.0        # front row swapped, podium named
    assert out["standings"]["top10"] == 1.0 and out["standings"]["top1"] == 0.0
    assert out["grid"]["rmse"] == pytest.approx(np.sqrt(2 / 10), abs=1e-3)


async def test_the_championship_order_going_into_a_race_counts_only_earlier_races():
    raw = synthetic_raw(years=[2024, 2025], rounds_per_year=6).assign(points=lambda d: (5 - d["position"]).clip(lower=0))
    out = PredictionService(model_dir="unused")._walk_forward_fit(raw, FakeLgb(), years_back=3)

    by_round = {r["round"]: r for r in out["races"] if r["year"] == 2025}
    leader_after_r1 = max(by_round[1]["drivers"], key=lambda d: -d["actual_position"])   # won round 1
    assert {d["driver_id"]: d["standings_rank"] for d in by_round[2]["drivers"]}[leader_after_r1["driver_id"]] == 1


async def test_auc_is_the_chance_a_hit_ranks_above_a_miss():
    assert backtest_scores._auc(np.array([0.9, 0.8, 0.1, 0.2]), np.array([1, 1, 0, 0])) == 1.0
    assert backtest_scores._auc(np.array([0.5, 0.5]), np.array([1, 0])) == 0.5
