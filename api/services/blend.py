"""
The LightGBM ranker blended with a linear model, and what drove each prediction (Phase 5, #34).

**Blend.** A ridge regression on the same inputs (minus the label-encoded ids, which mean nothing to
a linear model), standardised, with the same time weights, scored next to the ranker; the session's
score is z(ranker) + BLEND_WEIGHT * z(linear) within the session. Walk-forward (85 races 2023-26):
qualifying 3.20 -> 2.97 places off (paired t = -6.2), race 3.28 -> 3.23 (t = -2.1), sprint
2.87 -> 2.74; win / podium chances slightly better, pole slightly worse (0.0350 -> 0.0356). The
linear model alone did about as well as the ranker (qualifying 3.00) and a more regularised ranker
worse (3.31): the two make different mistakes. Weights 0.25-3 and ridge alpha 1-100 were all within
noise of each other; the equal blend was set before trying them.

**Why.** Each score splits into what every input added (LightGBM's own per-tree contributions,
`pred_contrib` — no SHAP library — plus the linear terms), measured against the session's average
driver, so "+" means it lifted the driver above the field. Inputs are grouped into FACTORS.
"""
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

BLEND_WEIGHT = 1.0
RIDGE_ALPHA = 10.0
NOT_LINEAR = {"driver_enc", "constructor_enc", "circuit_enc"}

# Inputs grouped the way the page explains them.
FACTORS = {
    "Recent form": ["driver_rolling_finish", "driver_rolling_grid", "driver_season_avg_grid", "driver_season_points"],
    "Team": ["constructor_rolling_finish", "team_season_points", "constructor_enc"],
    "This circuit": ["driver_circuit_avg", "driver_circuit_grid_avg", "constructor_circuit_avg", "circuit_enc", "round"],
    "Practice": ["driver_practice_best_rank", "driver_practice_gap_pct", "team_practice_gap_pct",
                 "driver_practice_teammate_gap_pct"],
    "Starting grid": ["grid", "sprint_grid"],
    "Reliability": ["driver_dnf_rate"],
    "Driver": ["driver_enc"],
    "Preseason testing": ["driver_testing_gap_pct", "team_testing_gap_pct"],
}
FACTOR_OF = {f: name for name, feats in FACTORS.items() for f in feats}


def _z(v: np.ndarray) -> np.ndarray:
    sd = v.std()
    return (v - v.mean()) / (sd if sd > 0 else 1.0)


class BlendedRanker:
    """Quacks like the LGBMRanker it wraps (.predict(X)); scores are relative within the session."""

    def __init__(self, ranker, features: List[str], weight: float = BLEND_WEIGHT):
        self.ranker, self.features, self.weight = ranker, list(features), weight
        self.linear_features = [f for f in features if f not in NOT_LINEAR]
        self.ridge = None
        self.mean: Optional[pd.Series] = None
        self.std: Optional[pd.Series] = None

    def fit_linear(self, X: pd.DataFrame, relevance: np.ndarray, sample_weight=None) -> "BlendedRanker":
        from sklearn.linear_model import Ridge
        Xl = X[self.linear_features].astype(float)
        self.mean, self.std = Xl.mean(), Xl.std().replace(0, 1).fillna(1)
        self.ridge = Ridge(alpha=RIDGE_ALPHA).fit(((Xl - self.mean) / self.std).fillna(0).values, relevance,
                                                  sample_weight=sample_weight)
        return self

    def _standardised(self, X: pd.DataFrame) -> np.ndarray:
        return ((X[self.linear_features].astype(float) - self.mean) / self.std).fillna(0).values

    def predict(self, X, **kwargs) -> np.ndarray:
        X = X if isinstance(X, pd.DataFrame) else pd.DataFrame(X, columns=self.features)
        tree = np.asarray(self.ranker.predict(X[self.features], **kwargs), float)
        if self.ridge is None or not self.weight:
            return tree
        return _z(tree) + self.weight * _z(self.ridge.predict(self._standardised(X)))

    def contributions(self, X: pd.DataFrame) -> pd.DataFrame:
        """Per driver and input, what it added to the score, against the session's average driver
        (rows add up to the score minus its session mean)."""
        X = X[self.features]
        tree = np.asarray(self.ranker.predict(X, pred_contrib=True), float)[:, :-1]     # last column: bias
        tree_sd = tree.sum(axis=1).std() or 1.0
        out = pd.DataFrame(tree / (tree_sd if self.ridge is not None and self.weight else 1.0),
                           columns=self.features, index=X.index)
        if self.ridge is not None and self.weight:
            terms = self._standardised(X) * self.ridge.coef_[None, :]
            lin_sd = terms.sum(axis=1).std() or 1.0
            out[self.linear_features] += self.weight * terms / lin_sd
        return out - out.mean(axis=0)


def contributions(model, X: pd.DataFrame, features: List[str]) -> pd.DataFrame:
    """Per-input contributions for a BlendedRanker or a plain LGBMRanker (saved before Phase 5)."""
    if hasattr(model, "contributions"):
        return model.contributions(X)
    c = pd.DataFrame(np.asarray(model.predict(X[features], pred_contrib=True), float)[:, :-1],
                     columns=features, index=X.index)
    return c - c.mean(axis=0)


OTHER = "Other"


def factors(contrib: pd.DataFrame, X: Optional[pd.DataFrame] = None) -> List[Dict[str, float]]:
    """Per driver: {factor: effect}, the inputs summed into FACTORS (an input not listed goes to
    its own name). An input that's the same for every driver in `X` (practice before any has run:
    everyone gets the neutral value) can't be why one is ahead of another, but the trees still
    credit it a little through interactions — it goes to OTHER, which the page doesn't show."""
    constant = {c for c in contrib.columns if X is not None and c in X and X[c].nunique(dropna=False) <= 1}
    grouped = contrib.T.groupby(lambda f: OTHER if f in constant else FACTOR_OF.get(f, f)).sum().T
    return [{k: round(float(v), 3) for k, v in row.items() if abs(v) >= 1e-6} for _, row in grouped.iterrows()]
