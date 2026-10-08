"""Team form (constructor_rolling_finish, constructor_circuit_avg) only sees races before the one it's
for. It used to be rolled over driver rows, so one teammate's row took in the other's finish from the
same race — the answer leaking into the inputs, and the qualifying model's inputs too."""
import pandas as pd
import pytest

from services import prediction_service as ps
from services.prediction_service import PredictionService
from tests.test_prediction_training import synthetic_raw

TEAM = ["constructor_rolling_finish", "constructor_circuit_avg"]


def engineered(raw):
    return PredictionService(model_dir="unused")._engineer(raw).set_index(["race_id", "driver_id"])[TEAM]


def test_a_races_own_results_never_reach_its_team_form():
    raw = synthetic_raw(years=[2025], rounds_per_year=6)
    shuffled = raw.copy()
    rows = shuffled.index[shuffled["race_id"] == "2025_4"]
    shuffled.loc[rows, "position"] = shuffled.loc[rows, "position"].to_numpy()[::-1]

    before, after = engineered(raw), engineered(shuffled)

    same_race = [i for i in before.index if i[0] == "2025_4"]
    pd.testing.assert_frame_equal(before.loc[same_race], after.loc[same_race])
    next_race = [i for i in before.index if i[0] == "2025_5"]
    assert not before.loc[next_race].equals(after.loc[next_race])        # it's in the next race's form


def test_both_cars_share_their_teams_form_the_mean_of_its_last_races(monkeypatch):
    monkeypatch.setattr(ps, "TEAM_FORM_RACES", 2)
    df = pd.DataFrame({
        "year": [2025] * 6, "round": [1, 1, 2, 2, 3, 3], "constructor_id": ["mcl"] * 6,
        "driver_id": ["nor", "pia"] * 3, "circuit_name": ["a", "a", "b", "b", "a", "a"],
        "position": [1, 5, 2, 4, 3, 9],
    })

    out = PredictionService._team_form(df)

    third = out[out["round"] == 3]
    assert third["constructor_rolling_finish"].tolist() == [3.0, 3.0]    # races 1 and 2: (1+5)/2, (2+4)/2
    assert third["constructor_circuit_avg"].tolist() == [3.0, 3.0]       # race 1 at circuit a
    assert out.loc[out["round"] == 1, "constructor_rolling_finish"].isna().all()


@pytest.mark.parametrize("missing", ["constructor", "result"])
def test_rows_without_a_team_or_a_result_dont_break_it(missing):
    raw = synthetic_raw(years=[2025], rounds_per_year=4)
    if missing == "constructor":
        raw.loc[raw.index[0], "constructor_id"] = None
    else:
        raw.loc[raw["race_id"] == "2025_4", "position"] = float("nan")     # a weekend whose race is still to run
    out = engineered(raw)
    assert len(out) == len(raw)
    assert out.loc[[i for i in out.index if i[0] == "2025_4"], "constructor_rolling_finish"].notna().all()
