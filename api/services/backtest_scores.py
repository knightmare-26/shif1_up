"""
How good the finish odds were, race by race (Predictions → Predicted vs Actual).

The backtest's held-out models give every driver a score per session. Here each scored session is
played out with the same Plackett-Luce simulation the Predictions page uses, with its strength
(beta) fitted only on sessions that came **before** it — so a race's chances never learn from that
race or anything later. The chances are then scored against what happened:

- Brier score (mean squared error of the probability; lower is better) and log loss;
- the same for two baselines: *uniform* (everyone equal) and, for the race, *starting slot* — how
  often a car from that grid slot has won / podiumed / scored in earlier races;
- a reliability table: in each band of predicted chance, how often it actually happened.
"""
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np

from services.championship_service import BETA_GRID, pl_log_likelihood, sample_orders

SIMULATIONS = 5000
MIN_HISTORY = 10                 # sessions needed before beta is fitted (and chances are given)
# (market, top-n, the driver-row key that carries the chance)
MARKETS = {
    "race": [("win", 1, "win_probability"), ("podium", 3, "podium_probability"), ("points", 10, "points_probability")],
    "qualifying": [("pole", 1, "pole_probability"), ("top3", 3, "quali_top3_probability"), ("q3", 10, "q3_probability")],
}
FIELDS = {"race": ("race_score", "actual_position"), "qualifying": ("quali_score", "actual_grid")}
BANDS = [0.0, 0.05, 0.15, 0.3, 0.5, 0.75, 1.0]
EPS = 1e-4


def _scored(race: Dict[str, Any], kind: str) -> List[Dict[str, Any]]:
    score, actual = FIELDS[kind]
    return [d for d in race["drivers"] if d.get(score) is not None and d.get(actual) is not None]


def _ll_curve(scores_in_finish_order: np.ndarray) -> np.ndarray:
    return np.array([pl_log_likelihood(scores_in_finish_order, b) for b in BETA_GRID])


def _metrics(p: np.ndarray, y: np.ndarray) -> Dict[str, float]:
    q = np.clip(p, EPS, 1 - EPS)
    return {"brier": round(float(np.mean((p - y) ** 2)), 4),
            "log_loss": round(float(-np.mean(y * np.log(q) + (1 - y) * np.log(1 - q))), 4)}


def _reliability(p: np.ndarray, y: np.ndarray) -> List[Dict[str, Any]]:
    out = []
    for lo, hi in zip(BANDS, BANDS[1:]):
        inside = (p >= lo) & ((p < hi) if hi < 1 else (p <= hi))
        if inside.any():
            out.append({"from": lo, "to": hi, "n": int(inside.sum()),
                        "predicted": round(float(p[inside].mean()), 4), "observed": round(float(y[inside].mean()), 4)})
    return out


class _SlotHistory:
    """How often each starting slot has reached the top n so far (smoothed toward n / field)."""

    PRIOR_WEIGHT = 2.0

    def __init__(self):
        self.hits: Dict[Tuple[int, int], float] = {}
        self.starts: Dict[int, float] = {}

    def chance(self, slot: int, top: int, field: int) -> float:
        prior = top / field
        return (self.hits.get((slot, top), 0.0) + self.PRIOR_WEIGHT * prior) / (self.starts.get(slot, 0.0) + self.PRIOR_WEIGHT)

    def add(self, slot: int, finish: int, tops: Sequence[int]) -> None:
        self.starts[slot] = self.starts.get(slot, 0.0) + 1
        for top in tops:
            if finish <= top:
                self.hits[(slot, top)] = self.hits.get((slot, top), 0.0) + 1


def add_probabilities(races: List[Dict[str, Any]], seed: int = 0) -> Dict[str, Any]:
    """Give each driver row in `races` its chances (keys in MARKETS) and return the scores.
    Sessions are processed in date order; each one's beta comes from the sessions before it."""
    rng = np.random.default_rng(seed)
    curves = {kind: np.zeros(len(BETA_GRID)) for kind in MARKETS}
    seen = {kind: 0 for kind in MARKETS}
    slots = _SlotHistory()
    pairs: Dict[str, Dict[str, Dict[str, list]]] = {
        kind: {m: {"model": [], "uniform": [], "slot": [], "y": []} for m, _, _ in markets}
        for kind, markets in MARKETS.items()
    }
    scored_races = 0

    for race in sorted(races, key=lambda r: (r["year"], r["round"])):
        for d in race["drivers"]:
            for markets in MARKETS.values():
                for _, _, key in markets:
                    d.pop(key, None)
        given = False
        for kind, markets in MARKETS.items():
            rows = _scored(race, kind)
            if len(rows) < 2:
                continue
            score_key, actual_key = FIELDS[kind]
            scores = np.array([float(d[score_key]) for d in rows])
            actual = np.array([int(d[actual_key]) for d in rows])
            field = len(rows)

            if seen[kind] >= MIN_HISTORY:
                beta = float(BETA_GRID[int(np.argmax(curves[kind]))])
                pos = sample_orders(scores, beta, SIMULATIONS, rng)
                given = True
                for market, top, key in markets:
                    chance = (pos < top).mean(axis=0)
                    hit = (actual <= top).astype(float)
                    for d, c in zip(rows, chance):
                        d[key] = round(float(c), 4)
                    bucket = pairs[kind][market]
                    bucket["model"].extend(chance)
                    bucket["uniform"].extend([min(1.0, top / field)] * field)
                    bucket["y"].extend(hit)
                    if kind == "race":
                        bucket["slot"].extend(slots.chance(int(d["actual_grid"] or field), top, field) if d.get("actual_grid")
                                              else min(1.0, top / field) for d in rows)

            curves[kind] += _ll_curve(scores[np.argsort(actual, kind="stable")])
            seen[kind] += 1

        for d in _scored(race, "race"):
            if d.get("actual_grid"):
                slots.add(int(d["actual_grid"]), int(d["actual_position"]), [t for _, t, _ in MARKETS["race"]])
        scored_races += given

    out: Dict[str, Any] = {"races_scored": scored_races, "simulations": SIMULATIONS, "min_history": MIN_HISTORY}
    for kind, markets in MARKETS.items():
        out[kind] = {}
        for market, top, _ in markets:
            b = pairs[kind][market]
            if not b["y"]:
                continue
            y, p = np.array(b["y"]), np.array(b["model"])
            entry = {"top": top, "n": int(len(y)), "observed_rate": round(float(y.mean()), 4),
                     **_metrics(p, y), "uniform": _metrics(np.array(b["uniform"]), y),
                     "reliability": _reliability(p, y)}
            if b["slot"]:
                entry["starting_slot"] = _metrics(np.array(b["slot"]), y)
            # Brier skill: 1 = perfect, 0 = no better than the baseline, below 0 = worse.
            for name in ("uniform", "starting_slot"):
                if name in entry and entry[name]["brier"]:
                    entry[f"skill_vs_{name}"] = round(1 - entry["brier"] / entry[name]["brier"], 4)
            out[kind][market] = entry
    return out
