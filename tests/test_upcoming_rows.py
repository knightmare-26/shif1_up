"""An upcoming race is predicted from the same inputs the walk-forward backtest scores it with once it's
run: form after each driver's latest race, the team's after its latest. They used to be the form going
INTO the latest race (one race out of date), a returning driver got the team's form from their own last
race, and the round was the one the circuit usually is."""
import pandas as pd
import pytest

from services.prediction_service import PredictionService
from tests.test_prediction_training import synthetic_raw

INPUTS = ["driver_rolling_finish", "driver_rolling_grid", "driver_circuit_avg", "driver_circuit_grid_avg",
          "constructor_rolling_finish", "constructor_circuit_avg", "driver_dnf_rate",
          "driver_season_points", "driver_season_avg_grid", "team_season_points", "round"]


def season_data():
    raw = synthetic_raw(years=[2024, 2025], rounds_per_year=6)
    raw["points"] = (5 - raw["position"]).clip(lower=0).astype(float)
    raw.loc[raw.index[::7], "status"] = "Retired"                                        # some DNFs
    raw = raw[~((raw["year"] == 2025) & (raw["round"] == 5) & (raw["driver_id"] == "d4"))]   # d4 misses round 5
    moved = (raw["year"] == 2025) & (raw["round"] == 6) & (raw["driver_id"] == "d3")
    raw.loc[moved, ["constructor_id", "constructor_name"]] = ["c1", "Team 1"]               # d3 changes teams
    return raw.reset_index(drop=True)


@pytest.mark.parametrize("year,rnd", [(2025, 6), (2025, 1)])
def test_an_upcoming_races_inputs_are_the_ones_its_row_gets_once_run(year, rnd):
    svc = PredictionService(model_dir="unused")
    full = svc._engineer(season_data())
    race = full[(full["year"] == year) & (full["round"] == rnd)].set_index("driver_id")
    history = full[(full["year"] < year) | ((full["year"] == year) & (full["round"] < rnd))]

    rows = svc._build_prediction_rows(f"circuit{rnd}", df=history, field=race["constructor_id"].to_dict(),
                                      season=year, use_testing=False, round_no=rnd).set_index("driver_id")

    pd.testing.assert_frame_equal(rows.loc[race.index, INPUTS].astype(float), race[INPUTS].astype(float),
                                  check_exact=False, atol=1e-9)


def test_models_saved_before_the_after_inputs_still_predict():
    svc = PredictionService(model_dir="unused")
    full = svc._engineer(season_data())
    old = full.drop(columns=[c for c in full if c.endswith("_after") and c != "driver_season_points_after"
                             and c != "team_season_points_after" and c != "driver_season_avg_grid_after"])

    rows = svc._build_prediction_rows("circuit3", df=old, season=2025, use_testing=False)

    assert len(rows) == 4 and rows["driver_rolling_finish"].notna().all()
