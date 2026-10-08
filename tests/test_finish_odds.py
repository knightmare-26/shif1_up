"""Phase 4 (#33): finish chances from one strength per driver (services/finish_odds.py)."""
import numpy as np
import pytest

from services import finish_odds as fo
from services.backtest_scores import add_probabilities


def simulated_races(n_races, beta=1.0, gamma=0.0, n=20, seed=0, retire=0.0):
    """Races drawn from the model itself: strength = beta * score - gamma * log(grid)."""
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n_races):
        scores = rng.normal(0, 1, n)
        grid = rng.permutation(n) + 1
        u = beta * scores - gamma * np.log(grid) + rng.gumbel(size=n)
        out_ = rng.random(n) < retire
        u[out_] = -1e9
        actual = np.argsort(np.argsort(-u)) + 1
        statuses = ["Engine" if o else "Finished" for o in out_]
        out.append((scores, actual, grid, statuses))
    return out


def test_the_fit_finds_the_spread_on_the_front_of_the_order():
    model = fo.FinishOdds("qualifying")
    for scores, actual, _, _ in simulated_races(150, beta=1.0):
        model.add(scores, actual)
    assert model.params["beta"] == pytest.approx(1.0, rel=0.3)


def test_a_race_learns_how_much_the_grid_matters():
    model = fo.FinishOdds("race")
    for scores, actual, grid, statuses in simulated_races(150, beta=0.5, gamma=1.5):
        model.add(scores, actual, grid, statuses)
    assert model.params["gamma"] == pytest.approx(1.5, abs=0.4)

    no_grid = fo.FinishOdds("race")
    for scores, actual, grid, statuses in simulated_races(150, beta=0.5, gamma=0.0):
        no_grid.add(scores, actual, grid, statuses)
    assert no_grid.params["gamma"] < 0.4


def test_retirements_are_left_out_of_the_fit_and_cost_a_driver_chances():
    model = fo.FinishOdds("race")
    for scores, actual, grid, statuses in simulated_races(80, beta=1.0, retire=0.15):
        model.add(scores, actual, grid, statuses)
    assert model.params["beta"] == pytest.approx(1.0, rel=0.35)      # retired cars don't flatten it

    scores = np.array([2.0, 2.0, 0.0, -1.0])
    reliable, fragile = model.predict(scores, [1, 1, 3, 4], [0.0, 0.6, 0.1, 0.1], sims=20000)["podium"][:2]
    assert reliable > fragile


def test_chances_add_up_and_follow_the_strength():
    model = fo.FinishOdds("race")
    for scores, actual, grid, statuses in simulated_races(20, beta=1.0, gamma=1.0):
        model.add(scores, actual, grid, statuses)
    pred = model.predict(np.array([1.0, 0.5, 0.0, -0.5, -1.0]), [1, 2, 3, 4, 5], sims=20000)
    assert pred["win"].sum() == pytest.approx(1, abs=1e-6) and pred["podium"].sum() == pytest.approx(3, abs=1e-6)
    ordered = fo.in_strength_order(pred["win"], pred["strength"])
    assert list(ordered) == sorted(ordered, reverse=True)


def test_qualifying_gets_a_correction_curve_once_there_is_enough_history():
    model = fo.FinishOdds("qualifying")
    races = simulated_races(40, beta=2.0)
    for scores, actual, _, _ in races:
        if model.ready:
            model.record(model.predict(scores, sims=500)["raw"], actual)
        model.add(scores, actual)
    assert len(model._pairs["pole"][0]) >= fo.MIN_PAIRS
    pred = model.predict(races[0][0], sims=2000)
    assert pred["pole"].sum() == pytest.approx(1, abs=1e-6) and "pole" in model._curves


def test_the_backtest_orders_a_race_by_strength_and_keeps_the_models_own_order():
    races = []
    for i, (scores, actual, grid, statuses) in enumerate(simulated_races(14, beta=0.3, gamma=2.0, n=12, seed=3)):
        model_rank = np.argsort(np.argsort(-scores)) + 1
        races.append({"year": 2025, "round": i + 1, "race_id": f"r{i}", "race_mae": 0, "drivers": [
            {"driver_id": f"d{k}", "race_score": float(scores[k]), "actual_position": int(actual[k]),
             "actual_grid": int(grid[k]), "predicted_position": int(model_rank[k]), "status": statuses[k],
             "quali_score": float(scores[k]), "actual_quali": int(grid[k])} for k in range(12)]})
    add_probabilities(races)

    late = races[-1]["drivers"]
    assert all("model_position" in d for d in late)
    assert [d["predicted_position"] for d in late] != [d["model_position"] for d in late]   # the grid moved it
    assert "model_position" not in races[0]["drivers"][0]                                   # too early to fit
    again = [d["predicted_position"] for d in late]
    add_probabilities(races)                                                                 # a rebuild: same answer
    assert [d["predicted_position"] for d in races[-1]["drivers"]] == again
