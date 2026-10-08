"""
Finish chances and the final order of a session (Phase 4, #33).

Each driver gets one strength, and the session is played out thousands of times (Plackett-Luce):

    race:        strength = beta * model score - gamma * log(grid position), with retirements
                 drawn first (each driver's own recent DNF rate, shrunk toward the field's)
    qualifying:  strength = beta * model score, then a correction curve per market (isotonic)

beta and gamma are fitted by likelihood on the **top TOP_K finishers** of earlier sessions — the
whole order is mostly midfield shuffling, which made one beta far too cautious at the front
(drivers given ~19% to win won 56%). The grid term lets the race chances, and the order, use how
much the starting position decides a race on top of the model's score; one strength per driver
means the chances can never contradict the order.

Walk-forward (85 races 2023-26, race with the grid known), Brier: win 0.0376 -> 0.0258, podium
0.0886 -> 0.0678, points 0.1734 -> 0.1530 — all now better than the history of each grid slot
(0.0312 / 0.0695 / 0.1647); ordering by strength: 3.45 -> 3.24 places off (the grid: 3.32),
podium named 63% -> 68% (the grid: 67%). Qualifying: pole 0.0386 -> 0.0355, top 3 0.0888 ->
0.0836, Q3 0.1535 -> 0.1398. Tried and not kept: a blend with the grid-slot history after the
simulation (as good, but contradicts the order — keeping order cost most of its gain), separate
spreads for the leaders and the rest, a per-circuit spread (no effect).
"""
from typing import Any, Dict, List, Optional

import numpy as np

TOP_K = 5
MIN_HISTORY = 10            # sessions before the fit is trusted
SIMULATIONS = 20000
DNF_SHRINK = 0.5            # a driver's retirement chance: halfway between their rate and the prior
DNF_PRIOR = 0.1
MIN_PAIRS = 200             # (chance, outcome) pairs before a correction curve is fitted
BETAS = np.logspace(-2, 1.5, 36)
GAMMAS = np.linspace(0, 3, 31)
MARKETS = {"race": [("win", 1), ("podium", 3), ("points", 10)],
           "qualifying": [("pole", 1), ("top3", 3), ("q3", 10)]}


def finished(status: Optional[str]) -> bool:
    """A classified finisher ("Finished", "+1 Lap"); unknown counts as finished."""
    s = status or ""
    return s == "" or s.startswith("Finished") or s.startswith("+") or "Lap" in s


class FinishOdds:
    def __init__(self, kind: str):
        self.kind = kind
        self.uses_grid = kind == "race"
        self.retirements = kind == "race"
        gammas = GAMMAS if self.uses_grid else GAMMAS[:1]
        self._gammas = gammas
        self._ll = np.zeros((len(BETAS), len(gammas)))
        self.sessions = 0
        self._pairs: Dict[str, List[List[float]]] = {m: [[], []] for m, _ in MARKETS[kind]}
        self._curves: Dict[str, Any] = {}
        self._curve_size: Dict[str, int] = {}

    # ---- fitting -------------------------------------------------------------------------------

    @property
    def ready(self) -> bool:
        return self.sessions >= MIN_HISTORY

    @property
    def params(self) -> Dict[str, float]:
        i, j = np.unravel_index(int(np.argmax(self._ll)), self._ll.shape)
        return {"beta": float(BETAS[i]), "gamma": float(self._gammas[j])}

    def add(self, scores, actual, grid=None, statuses=None) -> None:
        """Learn from a finished session: model scores, actual positions (and grid, statuses)."""
        scores, actual = np.asarray(scores, float), np.asarray(actual, float)
        if len(scores) < 2:
            return
        lg = np.log(self._grid(grid, len(scores)))
        order = np.argsort(actual, kind="stable")
        if self.retirements and statuses is not None:
            done = np.array([finished(s) for s in statuses])
            order = order[done[order]]
        k = min(TOP_K, len(order))
        if k < 1:
            return
        # every (beta, gamma) at once: x[b, g, i] is the strength of the i-th finisher
        x = (BETAS[:, None, None] * scores[order][None, None, :]
             - self._gammas[None, :, None] * lg[order][None, None, :])
        tail = np.flip(np.logaddexp.accumulate(np.flip(x, axis=2), axis=2), axis=2)
        self._ll += (x - tail)[:, :, :k].sum(axis=2)
        self.sessions += 1

    def record(self, chances: Dict[str, np.ndarray], actual) -> None:
        """Keep a session's (simulated chance, outcome) pairs — `predict(...)["raw"]`, made before
        the session was learnt — for the correction curves."""
        if self.kind != "qualifying":
            return
        actual = np.asarray(actual, float)
        for market, top in MARKETS[self.kind]:
            self._pairs[market][0].extend(np.asarray(chances[market], float))
            self._pairs[market][1].extend((actual <= top).astype(float))

    # ---- predicting ----------------------------------------------------------------------------

    @staticmethod
    def _grid(grid, n: int) -> np.ndarray:
        if grid is None:
            return np.ones(n)
        g = np.array([x if x is not None and x == x and x > 0 else n for x in grid], float)
        return np.clip(g, 1, None)

    def strength(self, scores, grid=None) -> np.ndarray:
        p = self.params
        return p["beta"] * np.asarray(scores, float) - p["gamma"] * np.log(self._grid(grid, len(scores)))

    def predict(self, scores, grid=None, dnf_rates=None, seed: int = 0, sims: int = SIMULATIONS) -> Dict[str, Any]:
        """{"strength", "expected_position", <market>: chance per driver} — markets in MARKETS."""
        rng = np.random.default_rng(seed)
        strength = self.strength(scores, grid)
        n = len(strength)
        u = strength[None, :] + rng.gumbel(size=(sims, n))
        if self.retirements:
            given = [None] * n if dnf_rates is None else list(dnf_rates)
            rates = np.array([r if r is not None and r == r else DNF_PRIOR for r in given], float)
            q = DNF_SHRINK * rates + (1 - DNF_SHRINK) * DNF_PRIOR
            out = rng.random((sims, n)) < q[None, :]
            u[out] = -1e9 + rng.random(int(out.sum()))          # the retired go to the back, any order
        order = np.argsort(-u, axis=1)
        pos = np.empty_like(order)
        np.put_along_axis(pos, order, np.arange(n)[None, :].repeat(sims, 0), axis=1)
        result: Dict[str, Any] = {"strength": strength, "expected_position": pos.mean(axis=0) + 1, "raw": {}}
        for market, top in MARKETS[self.kind]:
            raw = (pos < top).mean(axis=0)
            result["raw"][market] = raw
            result[market] = self._corrected(market, top, raw)
        return result

    def _corrected(self, market: str, top: int, p: np.ndarray) -> np.ndarray:
        x, y = self._pairs[market]
        if len(x) < MIN_PAIRS:
            return p
        if self._curve_size.get(market) != len(x):
            from sklearn.isotonic import IsotonicRegression
            self._curves[market] = IsotonicRegression(y_min=0, y_max=1, out_of_bounds="clip").fit(x, y)
            self._curve_size[market] = len(x)
        c = self._curves[market].predict(p)
        return np.clip(c * min(top, len(p)) / max(c.sum(), 1e-9), 0, 1)


def in_strength_order(values: np.ndarray, strength: np.ndarray, higher_is_better: bool = True) -> np.ndarray:
    """The values re-dealt so a stronger driver never shows a worse one (simulation noise and
    individual retirement chances can otherwise swap near-equal drivers)."""
    by_strength = np.argsort(-strength, kind="stable")
    out = np.empty_like(values)
    out[by_strength] = np.sort(values)[::-1] if higher_is_better else np.sort(values)
    return out
