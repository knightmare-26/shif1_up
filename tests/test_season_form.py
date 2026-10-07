"""Phase 2 (#31): season-to-date form — average grid, driver and team points so far this season."""
import os
import pandas as pd
import pytest

from services.prediction_service import PredictionService
from services.season_form import add_season_form, team_points_after
from tests.test_prediction_training import FakeLgb, synthetic_raw


def season(rows):
    return pd.DataFrame(rows, columns=["year", "round", "driver_id", "constructor_id", "grid", "points"])


ROWS = [
    (2025, 1, "aaa", "fast", 1, 25), (2025, 1, "bbb", "fast", 3, 15), (2025, 1, "ccc", "slow", 2, 18),
    (2025, 2, "aaa", "fast", 2, 18), (2025, 2, "bbb", "fast", 1, 25), (2025, 2, "ccc", "slow", 5, 0),
    (2026, 1, "aaa", "fast", 4, 0), (2026, 1, "bbb", "fast", 1, 25), (2026, 1, "ccc", "slow", 2, 18),
]


def test_everything_is_from_before_the_race_within_its_season():
    df = add_season_form(season(ROWS)).set_index(["year", "round", "driver_id"])

    assert df.loc[(2025, 1, "aaa"), "driver_season_points"] == 0
    assert df.loc[(2025, 2, "aaa"), "driver_season_points"] == 25
    assert df.loc[(2025, 2, "aaa"), "driver_season_points_after"] == 43
    assert df.loc[(2025, 2, "bbb"), "team_season_points"] == 40          # both fast cars in round 1
    assert df.loc[(2025, 2, "aaa"), "driver_season_avg_grid"] == 1
    assert df.loc[(2025, 2, "aaa"), "driver_season_avg_grid_after"] == 1.5
    # a new season: no points yet, and last season's final average grid
    assert df.loc[(2026, 1, "aaa"), "driver_season_points"] == 0 and df.loc[(2026, 1, "aaa"), "team_season_points"] == 0
    assert df.loc[(2026, 1, "ccc"), "driver_season_avg_grid"] == 3.5


def test_team_points_after_the_latest_race_of_a_season():
    df = add_season_form(season(ROWS))
    assert team_points_after(df, 2025).to_dict() == {"fast": 83, "slow": 18}
    assert team_points_after(df, 2027).empty


DRIVERS = ("d1", "d2", "d3", "d4")


def trained(years):
    svc = PredictionService(model_dir=os.environ["MODEL_DIR"])
    raw = synthetic_raw(years=years, rounds_per_year=6, drivers=DRIVERS).assign(
        points=lambda d: (5 - d["position"]).clip(lower=0).astype(float))
    svc._fit(raw, FakeLgb())
    return svc


def test_the_next_race_is_predicted_from_the_form_after_the_latest_one():
    svc = trained([2025, 2026])
    rows = svc._build_prediction_rows("circuit1", season=2026).set_index("driver_id")
    last = svc._df[svc._df["year"] == 2026].sort_values("round").groupby("driver_id").last()

    for d in DRIVERS:
        assert rows.loc[d, "driver_season_points"] == last.loc[d, "driver_season_points_after"]
        assert rows.loc[d, "driver_season_avg_grid"] == pytest.approx(last.loc[d, "driver_season_avg_grid_after"])
    teams = team_points_after(svc._df, 2026)
    assert rows.loc["d1", "team_season_points"] == teams[last.loc["d1", "constructor_id"]]


def test_a_season_that_has_not_started_has_no_points_yet():
    svc = trained([2025, 2026])
    rows = svc._build_prediction_rows("circuit1", season=2027)

    assert (rows["driver_season_points"] == 0).all() and (rows["team_season_points"] == 0).all()
    assert rows["driver_season_avg_grid"].notna().all()


def test_the_models_use_the_season_form():
    svc = trained([2025, 2026])
    assert "driver_season_avg_grid" in svc._quali_features
    assert {"driver_season_points", "team_season_points"} <= set(svc._race_features)


def test_the_qualifying_model_learns_the_qualifying_result_not_the_grid():
    raw = synthetic_raw(years=[2025, 2026], rounds_per_year=6, drivers=DRIVERS).assign(points=0.0)
    quali = raw.copy().assign(session_type="qualifying", position=lambda d: d["grid"].rsub(5))   # differs from the grid
    quali = quali[quali["round"] != 6]                                                           # one weekend without qualifying
    svc = PredictionService(model_dir=os.environ["MODEL_DIR"])
    svc._fit(pd.concat([raw, quali], ignore_index=True), FakeLgb())

    df = svc._df.set_index(["year", "round", "driver_id"])
    row = df.loc[(2026, 1, "d1")]
    assert row["quali_target"] == row["quali_position"] != row["grid"]
    no_quali = df.loc[(2026, 6, "d1")]
    assert no_quali["quali_target"] == no_quali["grid"]                                          # falls back to the grid
