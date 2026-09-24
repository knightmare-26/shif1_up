"""Championship outlook: the exact title maths, the Plackett-Luce pieces, the season simulation
and the API views. The maths tests use hand-made tables, so they need no model or database."""
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import api.main as main
from api.main import app
from services.championship_service import (
    Round, clean_results, fit_beta, max_round_points, pl_log_likelihood, sample_orders,
    season_table, simulate_season, title_status,
)


def entry(points, wins=0, seconds=0):
    cb = np.zeros(30, dtype=int)
    cb[0], cb[1] = wins, seconds
    return {"points": float(points), "countback": cb}


def rounds(n, sprint_rounds=()):
    return [Round(i, f"GP{i}", f"C{i}", i in sprint_rounds) for i in range(1, n + 1)]


# --- scoring ----------------------------------------------------------------------------------

def test_max_points_per_round():
    assert max_round_points(False, 2026) == 25 and max_round_points(True, 2026) == 33
    assert max_round_points(False, 2026, team=True) == 43 and max_round_points(True, 2026, team=True) == 58
    assert max_round_points(False, 2024) == 26  # fastest-lap point until 2024


# --- exact status -----------------------------------------------------------------------------

def test_a_rival_who_can_still_overtake_keeps_the_title_open():
    table = {"a": entry(100), "b": entry(76)}
    status = title_status(table, rounds(1), 2026)      # b can score 25: 101 > 100

    assert status["alive"] == {"a": True, "b": True} and not status["clinched"]


def test_the_leader_clinches_when_no_one_can_catch_up():
    table = {"a": entry(100), "b": entry(74), "c": entry(10)}
    status = title_status(table, rounds(1), 2026)      # b's best is 99

    assert status["clinched"] and status["leader"] == "a"
    assert status["alive"] == {"a": True, "b": False, "c": False}


def test_a_tie_on_points_goes_to_countback():
    # b's best case ties a on 100 and adds a win: 3 wins beat a's 2, so b is still alive...
    assert title_status({"a": entry(100, wins=2), "b": entry(75, wins=2)}, rounds(1), 2026)["alive"]["b"]
    # ...but with 1 win + 1 new win = 2 wins against a's 3, b can only tie on points and lose.
    status = title_status({"a": entry(100, wins=3), "b": entry(75, wins=1)}, rounds(1), 2026)
    assert not status["alive"]["b"] and status["clinched"]


def test_a_sprint_weekend_adds_to_what_is_left():
    table = {"a": entry(100), "b": entry(70)}
    assert not title_status(table, rounds(1), 2026)["alive"]["b"]                   # 70 + 25 < 100
    assert title_status(table, rounds(1, sprint_rounds={1}), 2026)["alive"]["b"]    # 70 + 33 > 100


def test_teams_can_score_a_one_two():
    table = {"x": entry(300), "y": entry(260)}
    status = title_status(table, rounds(1), 2026, team=True)

    assert status["max_points_remaining"] == 43 and status["alive"]["y"]


def test_the_next_race_clinch_hint():
    table = {"a": entry(200), "b": entry(150)}
    status = title_status(table, rounds(3), 2026)      # 75 left; 50 left after the next race

    # Clinched after the next race needs 200 + m > 150 + 50, i.e. outscoring b by at least 1.
    assert status["next_race_clinch"] == {"round": 1, "race_name": "GP1", "rival": "b", "margin_needed": 1}
    # Out of reach at the next race: no hint.
    assert title_status({"a": entry(200), "b": entry(190)}, rounds(3), 2026)["next_race_clinch"] is None


def test_a_finished_season_is_decided():
    status = title_status({"a": entry(300), "b": entry(299)}, [], 2025)

    assert status["clinched"] and status["max_points_remaining"] == 0


# --- stored results ---------------------------------------------------------------------------

def test_standings_include_sprints_count_back_on_races_and_drop_stale_duplicates():
    results = clean_results(pd.DataFrame([
        {"round": 1, "session_type": "race", "driver_id": "a", "constructor_id": "x", "position": 1, "points": 25},
        {"round": 1, "session_type": "race", "driver_id": "b", "constructor_id": "x", "position": 2, "points": 18},
        {"round": 1, "session_type": "sprint", "driver_id": "b", "constructor_id": "x", "position": 1, "points": 8},
        {"round": 1, "session_type": "sprint", "driver_id": "b", "constructor_id": "x", "position": 99, "points": None},
    ]))
    drivers = season_table(results, "driver_id")
    teams = season_table(results, "constructor_id")

    assert drivers["b"]["points"] == 26 and drivers["b"]["countback"][0] == 0   # a sprint win isn't a GP win
    assert drivers["a"]["countback"][0] == 1
    assert teams["x"]["points"] == 51 and len(results) == 3


# --- Plackett-Luce ----------------------------------------------------------------------------

def test_log_likelihood_of_a_two_driver_race():
    # P(first beats second) = e^s1 / (e^s1 + e^s2) with strengths beta * score.
    assert pl_log_likelihood(np.array([1.0, 0.0]), 1.0) == pytest.approx(np.log(np.e / (np.e + 1)))


def test_fit_beta_recovers_the_beta_that_generated_the_races():
    rng = np.random.default_rng(0)
    scores = np.linspace(-3, 3, 20)
    races = []
    for _ in range(300):
        pos = sample_orders(scores, 0.8, 1, rng)[0]
        races.append(scores[np.argsort(pos)])          # scores in finishing order

    assert fit_beta(races) == pytest.approx(0.8, rel=0.15)


def test_sampled_orders_are_permutations_and_favour_the_strongest():
    pos = sample_orders(np.array([5.0, 0.0, -5.0]), 1.0, 2000, np.random.default_rng(1))

    assert (np.sort(pos, axis=1) == [0, 1, 2]).all()
    assert (pos[:, 0] == 0).mean() > 0.95


# --- simulation -------------------------------------------------------------------------------

def simulate(form_sd=0.0, **overrides):
    args = dict(
        driver_table={"a": entry(50), "b": entry(40), "gone": entry(45)},
        team_table={"x": entry(90), "y": entry(45)},
        entrants=["a", "b"],
        team_of={"a": "x", "b": "x"},
        round_scores=[(np.array([2.0, 0.0]), False), (np.array([2.0, 0.0]), True)],
        beta=1.0, n_sims=4000, rng=np.random.default_rng(3), form_sd=form_sd,
    )
    args.update(overrides)
    return simulate_season(**args)


def test_simulation_probabilities_add_up_and_teams_sum_their_cars():
    sims = simulate()
    d, t = sims["drivers"], sims["teams"]

    assert sum(s["title_probability"] for s in d.values()) == pytest.approx(1.0)
    assert all(sum(s["position_probabilities"]) == pytest.approx(1.0, abs=1e-3) for s in d.values())  # rounded to 4 dp
    # Two rounds with a sprint: the team's two cars always take 25+18 and 8+7 between them.
    assert t["x"]["projected_points"] == pytest.approx(90 + 43 + 43 + 15)
    assert d["a"]["title_probability"] > d["b"]["title_probability"]


def test_a_driver_no_longer_racing_keeps_their_points_but_gains_none():
    sims = simulate()

    assert sims["drivers"]["gone"]["projected_points"] == 45
    assert sims["teams"]["y"]["projected_points"] == 45


def test_form_shocks_widen_the_outcomes():
    tight = simulate(round_scores=[(np.array([1.0, 0.0]), False)] * 10)["drivers"]["b"]["title_probability"]
    loose = simulate(form_sd=2.0, round_scores=[(np.array([1.0, 0.0]), False)] * 10)["drivers"]["b"]["title_probability"]

    assert loose > tight


# --- API --------------------------------------------------------------------------------------

OUTLOOK = {
    "year": 2026, "status": "in_progress", "rounds_completed": 14, "rounds_total": 23,
    "remaining": [], "sprint_calendar_known": True, "method": {}, "computed_at": "t",
    "drivers": {"clinched": False, "champion": None, "standings": [{"id": "ant"}]},
    "constructors": {"clinched": False, "champion": None, "standings": [{"id": "mercedes"}]},
}


@pytest.fixture
def client(monkeypatch):
    calls = []

    async def fake_outlook(year, db, sprint_rounds=None):
        calls.append((year, sprint_rounds))
        return OUTLOOK

    async def fake_schedule(year, use_cache=True):
        return [{"round": 0, "is_sprint": False}, {"round": 2, "is_sprint": True}, {"round": 3, "is_sprint": False}]

    monkeypatch.setattr(main.championship_service, "outlook", fake_outlook)
    monkeypatch.setattr(main, "legacy_race_schedule", fake_schedule)
    with TestClient(app) as c:
        c.calls = calls
        yield c


def test_the_drivers_and_constructors_views_share_one_outlook(client):
    d = client.get("/api/predictions/championship?year=2026").json()
    c = client.get("/api/predictions/constructors-championship?year=2026").json()

    assert d["standings"] == [{"id": "ant"}] and c["standings"] == [{"id": "mercedes"}]
    assert d["rounds_completed"] == c["rounds_completed"] == 14
    assert client.calls == [(2026, {2}), (2026, {2})]   # sprint rounds come from the schedule


def test_the_championship_backtest_is_empty_until_computed(client):
    assert client.get("/predict/championship/backtest").json()["seasons"] == []
