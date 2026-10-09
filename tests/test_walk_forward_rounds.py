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
             "quali_score": float(scores[k]), "actual_quali": int(k + 1), "actual_grid": int(k + 1)} for k in range(10)]})
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
         "predicted_grid": m, "actual_quali": a}
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


# --- a weekend still in progress ----------------------------------------------------------------

def with_session(raw, year, rnd, session_type, order, grid=None):
    """`raw` plus one finished session of round `rnd` (drivers in `order`, first = P1)."""
    import pandas as pd
    rows = [{"race_id": f"{year}_{rnd}", "driver_id": d, "constructor_id": f"c{int(d[1:]) % 2}",
             "position": i, "grid": (grid or {}).get(d, float("nan")), "points": 0.0, "status": "", "session_type": session_type,
             "circuit_name": f"circuit{rnd}", "year": year, "round": rnd, "race_name": f"GP{rnd}",
             "driver_name": d, "constructor_name": "Team"} for i, d in enumerate(order, start=1)]
    return pd.concat([raw, pd.DataFrame(rows)], ignore_index=True)


async def test_a_finished_qualifying_is_scored_before_its_race_is_run():
    raw = with_session(synthetic_raw(years=[2024, 2025], rounds_per_year=6), 2025, 7, "qualifying",
                       ["d3", "d1", "d4", "d2"])

    out = PredictionService(model_dir="unused")._walk_forward_fit(raw, FakeLgb(), years_back=3)

    weekend = next(r for r in out["races"] if r["round"] == 7)
    assert weekend["in_progress"] and weekend["sessions_done"] == ["qualifying"]
    assert weekend["unit"] == "2025-r7" and weekend["race_mae"] is None and weekend["quali_mae"] is not None
    assert [d["actual_quali"] for d in weekend["drivers"]] == [1, 2, 3, 4]       # in qualifying order
    assert all(d.get("predicted_position") is None for d in weekend["drivers"])
    assert not any(r.get("in_progress") for r in out["races"] if r["round"] != 7)


async def test_a_finished_sprint_is_scored_from_its_sprint_qualifying_grid():
    raw = synthetic_raw(years=[2024, 2025], rounds_per_year=6)
    raw = with_session(raw, 2025, 7, "sprint_qualifying", ["d1", "d2", "d3", "d4"])
    raw = with_session(raw, 2025, 7, "sprint", ["d2", "d1", "d3", "d4"], grid={"d1": 1, "d2": 2, "d3": 3, "d4": 4})
    # sprints earlier in the data, so there's a sprint model to score it with
    for year, rnd in [(2024, r) for r in range(1, 7)] + [(2025, 3), (2025, 5)]:
        raw = with_session(raw, year, rnd, "sprint", ["d1", "d2", "d3", "d4"], grid={"d1": 1, "d2": 2, "d3": 3, "d4": 4})

    weekend = next(r for r in PredictionService(model_dir="unused")._walk_forward_fit(raw, FakeLgb(), years_back=3)["races"]
                   if r["round"] == 7)

    assert weekend["in_progress"] and weekend["sessions_done"] == ["sprint_qualifying", "sprint"]
    assert sorted(d["actual_sprint"] for d in weekend["drivers"]) == [1, 2, 3, 4]
    # sprint qualifying is scored too, by the qualifying model
    assert {d["driver_id"]: d["actual_sq"] for d in weekend["drivers"]} == {"d1": 1, "d2": 2, "d3": 3, "d4": 4}
    assert all(d.get("predicted_sq") for d in weekend["drivers"]) and weekend["sq_mae"] is not None
    assert {d["driver_id"]: d["sprint_grid"] for d in weekend["drivers"]} == {"d1": 1, "d2": 2, "d3": 3, "d4": 4}


async def test_once_the_race_is_run_the_weekend_is_scored_like_any_other():
    svc = PredictionService(model_dir="unused")
    full = synthetic_raw(years=[2024, 2025], rounds_per_year=7)
    before_race = with_session(full[~((full["year"] == 2025) & (full["round"] == 7))], 2025, 7, "qualifying",
                               ["d1", "d2", "d3", "d4"])
    before = svc._walk_forward_fit(before_race, FakeLgb(), years_back=3)

    after = svc._walk_forward_fit(with_session(full, 2025, 7, "qualifying", ["d1", "d2", "d3", "d4"]), FakeLgb(),
                                  years_back=3, previous=copy.deepcopy(before))

    weekend = [r for r in after["races"] if r["round"] == 7 and r["year"] == 2025]
    assert len(weekend) == 1 and not weekend[0].get("in_progress") and weekend[0]["race_mae"] is not None
    assert after["refits"] == 1


async def test_an_old_weekend_missing_its_race_is_not_treated_as_under_way():
    """Only weekends after the latest race are in progress; an older gap is data upkeep's job."""
    full = synthetic_raw(years=[2024, 2025], rounds_per_year=6)
    raw = with_session(full[~((full["year"] == 2025) & (full["round"] == 3))], 2025, 3, "qualifying", ["d1", "d2", "d3", "d4"])

    out = PredictionService(model_dir="unused")._walk_forward_fit(raw, FakeLgb(), years_back=3)

    assert not any(r.get("in_progress") for r in out["races"])


def sq_race(n, rng):
    """A weekend with qualifying and sprint qualifying, higher scores ahead in both."""
    drivers = []
    for i in range(10):
        score = float(10 - i + rng.normal(0, 1))
        drivers.append({"driver_id": f"d{i}", "quali_score": score, "actual_quali": i + 1,
                        "sq_score": score, "actual_sq": i + 1,
                        "predicted_grid": i + 1, "predicted_sq": i + 1, "standings_rank": i + 1})
    return {"year": 2025, "round": n, "race_id": f"r{n}", "drivers": drivers}


async def test_sprint_qualifying_is_scored_with_the_qualifying_odds_but_never_fitted_on():
    rng = np.random.default_rng(3)
    races = [sq_race(n, rng) for n in range(1, 16)]
    only_quali = [{**r, "drivers": [{k: v for k, v in d.items() if k not in ("sq_score", "actual_sq")} for d in r["drivers"]]}
                  for r in copy.deepcopy(races)]

    scores = backtest_scores.add_probabilities(races)
    without = backtest_scores.add_probabilities(only_quali)

    assert "sprint_qualifying" in scores and scores["sprint_qualifying"]["pole"]["n"] > 0
    assert "sprint_qualifying" not in scores["method"]                       # no fit of its own
    assert scores["qualifying"] == without["qualifying"]                     # and it didn't train the qualifying one
    last = races[-1]["drivers"]
    assert all(d["sq_pole_probability"] == d["pole_probability"] for d in last)   # same scores, same chances
    assert "sprint_qualifying" in backtest_scores.hit_rates(races)
