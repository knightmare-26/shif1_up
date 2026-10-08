"""Phase 5 (#34): the ranker blended with a linear model, and what drove each prediction."""
import numpy as np
import pandas as pd
import pytest

from services import blend


class TreeStub:
    """Stands in for LGBMRanker: score = 2*a + b; pred_contrib returns those terms plus a bias."""
    def predict(self, X, pred_contrib=False):
        a, b = X["a"].to_numpy(float), X["b"].to_numpy(float)
        if pred_contrib:
            return np.column_stack([2 * a, b, np.zeros(len(a)), np.full(len(a), 5.0)])
        return 2 * a + b + 5


FEATURES = ["a", "b", "driver_enc"]


def frame(n=8, seed=0):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({"a": rng.normal(size=n), "b": rng.normal(size=n), "driver_enc": np.arange(n)})


def fitted(weight=1.0):
    X = frame(200, seed=1)
    relevance = (3 * X["a"] - X["b"]).to_numpy()
    return blend.BlendedRanker(TreeStub(), FEATURES, weight).fit_linear(X, relevance)


def test_the_blend_is_the_two_standardised_scores_added_up():
    model, X = fitted(), frame()
    tree = TreeStub().predict(X)
    linear = model.ridge.predict(model._standardised(X))
    z = lambda v: (v - v.mean()) / v.std()                                     # noqa: E731
    assert np.allclose(model.predict(X), z(tree) + z(linear))
    assert "driver_enc" not in model.linear_features                          # an id code means nothing linearly


def test_contributions_add_up_to_each_drivers_score_against_the_field():
    model, X = fitted(), frame()
    contrib = model.contributions(X)
    score = model.predict(X)
    assert np.allclose(contrib.sum(axis=1).to_numpy(), score - score.mean())
    assert np.allclose(contrib.mean(axis=0).to_numpy(), 0)


def test_inputs_are_grouped_into_the_pages_factors():
    contrib = pd.DataFrame({"driver_rolling_grid": [1.0, -1.0], "driver_season_points": [0.5, -0.5],
                            "grid": [0.2, -0.2], "driver_practice_gap_pct": [-0.3, 0.3]})
    rows = blend.factors(contrib)
    assert rows[0] == {"Recent form": 1.5, "Starting grid": 0.2, "Practice": -0.3}


def test_a_plain_ranker_saved_before_the_blend_still_explains_itself():
    X = frame()
    c = blend.contributions(TreeStub(), X, FEATURES)
    assert np.allclose(c["a"].to_numpy(), 2 * X["a"] - (2 * X["a"]).mean())


def test_an_input_the_same_for_everyone_is_never_shown_as_a_reason():
    contrib = pd.DataFrame({"driver_rolling_grid": [1.0, -1.0], "driver_practice_gap_pct": [-0.3, 0.3]})
    X = pd.DataFrame({"driver_rolling_grid": [2.0, 9.0], "driver_practice_gap_pct": [1.1, 1.1]})   # no practice yet
    rows = blend.factors(contrib, X)
    assert "Practice" not in rows[0] and rows[0]["Other"] == -0.3
