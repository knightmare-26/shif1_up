"""
How good the finish odds were, race by race (Predictions → Predicted vs Actual).

The backtest's held-out models give every driver a score per session. Here each scored session is
played out the way the Predictions page does it (services/finish_odds.py — a strength per driver
from the model score, and in a race the grid and retirements), fitted only on sessions that came
**before** it — so a race's chances never learn from that race or anything later. A race's order is
that strength's, as on the page. The chances are then scored against what happened:

- Brier score (mean squared error of the probability; lower is better) and log loss;
- the same for two baselines: *uniform* (everyone equal) and, for the race, *starting slot* — how
  often a car from that grid slot has won / podiumed / scored in earlier races;
- a reliability table: in each band of predicted chance, how often it actually happened;
- ROC-AUC: how well the chances separate the drivers who did it from those who didn't.

`hit_rates` scores the predicted *order* the plain way — did it pick the winner, how many of the
podium / top 5 / top 10 it named, position error (MAE, RMSE) — against two baselines: the starting
grid (the pole-sitter wins; race only) and the championship order before the weekend.
"""
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from services.finish_odds import MIN_HISTORY, FinishOdds, in_strength_order

SIMULATIONS = 5000
# (market, top-n, the driver-row key that carries the chance)
MARKETS = {
    "race": [("win", 1, "win_probability"), ("podium", 3, "podium_probability"), ("points", 10, "points_probability")],
    "sprint": [("win", 1, "sprint_win_probability"), ("podium", 3, "sprint_podium_probability"),
               ("points", 8, "sprint_points_probability")],
    # Sprint qualifying before qualifying: it's scored with the qualifying model's chances as they
    # stood before the weekend (the Predictions page uses the same fit), so it mustn't see this
    # weekend's qualifying.
    "sprint_qualifying": [("pole", 1, "sq_pole_probability"), ("top3", 3, "sq_top3_probability"),
                          ("q3", 10, "sq3_probability")],
    "qualifying": [("pole", 1, "pole_probability"), ("top3", 3, "quali_top3_probability"), ("q3", 10, "q3_probability")],
}
# Sessions predicted by another session's model and odds: scored with them, never fitted on.
BORROWED_ODDS = {"sprint_qualifying": "qualifying"}
FIELDS = {"race": ("race_score", "actual_position"), "sprint": ("sprint_score", "actual_sprint"),
          "qualifying": ("quali_score", "actual_quali"), "sprint_qualifying": ("sq_score", "actual_sq")}
GRID = {"race": "actual_grid", "sprint": "sprint_grid"}                 # the starting slot, for races
ORDER = {"race": "predicted_position", "sprint": "predicted_sprint"}     # re-ordered by strength
MAE = {"race": "race_mae", "sprint": "sprint_mae"}
BANDS = [0.0, 0.05, 0.15, 0.3, 0.5, 0.75, 1.0]
EPS = 1e-4


def _scored(race: Dict[str, Any], kind: str) -> List[Dict[str, Any]]:
    score, actual = FIELDS[kind]
    return [d for d in race["drivers"] if d.get(score) is not None and d.get(actual) is not None]


def _metrics(p: np.ndarray, y: np.ndarray) -> Dict[str, float]:
    q = np.clip(p, EPS, 1 - EPS)
    return {"brier": round(float(np.mean((p - y) ** 2)), 4),
            "log_loss": round(float(-np.mean(y * np.log(q) + (1 - y) * np.log(1 - q))), 4)}


def _auc(p: np.ndarray, y: np.ndarray) -> Optional[float]:
    """Probability that a random driver who did it got a higher chance than one who didn't."""
    pos, neg = p[y == 1], p[y == 0]
    if not len(pos) or not len(neg):
        return None
    order = np.argsort(np.concatenate([pos, neg]), kind="mergesort")
    ranks = np.empty(len(order))
    values = np.concatenate([pos, neg])[order]
    # average ranks for ties
    i = 0
    while i < len(values):
        j = i
        while j + 1 < len(values) and values[j + 1] == values[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2 + 1
        i = j + 1
    return round(float((ranks[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))), 4)


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
    Sessions are processed in date order, each predicted by a services/finish_odds.FinishOdds fitted
    on the sessions before it — the same method the Predictions page uses. A race is also re-ranked
    by that strength (the page's order); the model's own order is kept as `model_position`."""
    models = {kind: FinishOdds(kind) for kind in MARKETS if kind not in BORROWED_ODDS}
    slots = {kind: _SlotHistory() for kind in GRID}
    pairs: Dict[str, Dict[str, Dict[str, list]]] = {
        kind: {m: {"model": [], "uniform": [], "slot": [], "y": []} for m, _, _ in markets}
        for kind, markets in MARKETS.items()
    }
    scored_races = 0

    for n_race, race in enumerate(sorted(races, key=lambda r: (r["year"], r["round"]))):
        for d in race["drivers"]:
            for markets in MARKETS.values():
                for _, _, key in markets:
                    d.pop(key, None)
            if "model_position" in d:
                d["predicted_position"] = d["model_position"]
            if "model_sprint" in d:
                d["predicted_sprint"] = d["model_sprint"]
        given = False
        for kind, markets in MARKETS.items():
            rows = _scored(race, kind)
            if len(rows) < 2:
                continue
            score_key, actual_key = FIELDS[kind]
            scores = np.array([float(d[score_key]) for d in rows])
            actual = np.array([int(d[actual_key]) for d in rows])
            field = len(rows)
            is_race = kind in GRID
            grid = [d.get(GRID[kind]) for d in rows] if is_race else None
            borrowed = kind in BORROWED_ODDS
            model = models[BORROWED_ODDS.get(kind, kind)]

            if model.ready:
                pred = model.predict(scores, grid, [d.get("dnf_rate") for d in rows] if is_race else None,
                                     seed=seed + n_race, sims=SIMULATIONS)
                given = True
                if is_race:
                    order_key, own_key = ORDER[kind], "model_position" if kind == "race" else "model_sprint"
                    ranks = np.argsort(-pred["strength"], kind="stable").argsort() + 1
                    for d, rank in zip(rows, ranks):
                        d[own_key] = d.get(own_key, d.get(order_key))
                        d[order_key] = int(rank)
                    errs = [abs(d[order_key] - d[actual_key]) for d in rows]
                    race[MAE[kind]] = round(sum(errs) / len(errs), 2)
                for market, top, key in markets:
                    chance = in_strength_order(pred[market], pred["strength"])
                    hit = (actual <= top).astype(float)
                    for d, c in zip(rows, chance):
                        d[key] = round(float(c), 4)
                    bucket = pairs[kind][market]
                    bucket["model"].extend(chance)
                    bucket["uniform"].extend([min(1.0, top / field)] * field)
                    bucket["y"].extend(hit)
                    if is_race:
                        bucket["slot"].extend(slots[kind].chance(int(d[GRID[kind]]), top, field) if d.get(GRID[kind])
                                              else min(1.0, top / field) for d in rows)
                if not borrowed:
                    model.record(pred["raw"], actual)

            if not borrowed:
                model.add(scores, actual, grid, [d.get("status") for d in rows] if kind == "race" else None)

        for kind in GRID:
            for d in _scored(race, kind):
                if d.get(GRID[kind]):
                    slots[kind].add(int(d[GRID[kind]]), int(d[FIELDS[kind][1]]), [t for _, t, _ in MARKETS[kind]])
        scored_races += given

    out: Dict[str, Any] = {"races_scored": scored_races, "simulations": SIMULATIONS, "min_history": MIN_HISTORY,
                           "method": {kind: m.params for kind, m in models.items() if m.ready}}
    for kind, markets in MARKETS.items():
        out[kind] = {}
        for market, top, _ in markets:
            b = pairs[kind][market]
            if not b["y"]:
                continue
            y, p = np.array(b["y"]), np.array(b["model"])
            entry = {"top": top, "n": int(len(y)), "observed_rate": round(float(y.mean()), 4),
                     **_metrics(p, y), "auc": _auc(p, y), "uniform": _metrics(np.array(b["uniform"]), y),
                     "reliability": _reliability(p, y)}
            if b["slot"]:
                entry["starting_slot"] = _metrics(np.array(b["slot"]), y)
            # Brier skill: 1 = perfect, 0 = no better than the baseline, below 0 = worse.
            for name in ("uniform", "starting_slot"):
                if name in entry and entry[name]["brier"]:
                    entry[f"skill_vs_{name}"] = round(1 - entry["brier"] / entry[name]["brier"], 4)
            out[kind][market] = entry
    return out


# --- the predicted order, the plain way -------------------------------------------------------

HIT_TOPS = (1, 3, 5, 10)
# (session, actual key, {method: predicted-order key})
ORDERS = {
    "race": ("actual_position", {"model": "predicted_position", "grid": "actual_grid", "standings": "standings_rank"}),
    "sprint": ("actual_sprint", {"model": "predicted_sprint", "grid": "sprint_grid", "standings": "standings_rank"}),
    "qualifying": ("actual_quali", {"model": "predicted_grid", "standings": "standings_rank"}),
    "sprint_qualifying": ("actual_sq", {"model": "predicted_sq", "standings": "standings_rank"}),
}


def _ranked(rows: List[Dict[str, Any]], key: str) -> Dict[str, int]:
    """driver -> 1..n by `key` (lower is better), over the rows that have it."""
    have = sorted((r for r in rows if r.get(key) is not None), key=lambda r: r[key])
    return {r["driver_id"]: i + 1 for i, r in enumerate(have)}


def hit_rates(races: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Winner / podium / top-5 / top-10 hit rates and position errors for the model's predicted
    order and the baselines, over the races where all of them have an order to compare."""
    out: Dict[str, Any] = {}
    for kind, (actual_key, methods) in ORDERS.items():
        tally = {m: {"hits": {t: [] for t in HIT_TOPS}, "errors": []} for m in methods}
        races_used = 0
        for race in races:
            rows = [d for d in race["drivers"] if d.get(actual_key) is not None]
            orders = {m: _ranked(rows, key) for m, key in methods.items()}
            if len(rows) < 10 or any(len(o) < len(rows) for o in orders.values()):
                continue
            races_used += 1
            actual = _ranked(rows, actual_key)
            for m, order in orders.items():
                for top in HIT_TOPS:
                    named = {d for d, r in order.items() if r <= top}
                    did = {d for d, r in actual.items() if r <= top}
                    tally[m]["hits"][top].append(len(named & did) / top)
                tally[m]["errors"].extend(order[d] - actual[d] for d in actual)
        if not races_used:
            continue
        out[kind] = {"races": races_used}
        for m, t in tally.items():
            errors = np.array(t["errors"], dtype=float)
            out[kind][m] = {
                **{f"top{top}": round(float(np.mean(v)), 4) for top, v in t["hits"].items()},
                "mae": round(float(np.mean(np.abs(errors))), 3),
                "rmse": round(float(np.sqrt(np.mean(errors ** 2))), 3),
            }
    return out
