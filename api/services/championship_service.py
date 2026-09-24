"""
Championship outlook — drivers' and constructors' titles.

Two parts:

1. Exact maths (no model): who can still mathematically win, whether the title is already
   clinched, and what the leader needs at the next race to clinch it. Uses the scoring rules
   below and the countback tie-break (most wins, then most second places, ...).

2. A Monte Carlo projection: each remaining race's finishing order is drawn from the race
   ranker's scores with a Plackett-Luce model — P(driver i finishes ahead of the rest) is
   proportional to exp(beta * score_i), sampled with Gumbel noise. beta (how decisive the scores
   are) is fitted to real results the models had never seen: for each season, a model trained
   only on earlier seasons scores that season's races, and beta maximises the likelihood of the
   actual finishing orders. Retirements are part of those real orders, so they're priced in.
   Constructors come from the same simulated races, summed over each team's cars, so the two
   projections always agree.

Known simplifications: sprint orders reuse the race scores (too few sprints to calibrate their
own); the fastest-lap point (2019-2024) counts in the exact maths but isn't simulated; each race
is drawn independently, so a car that is quick for the rest of the season isn't modelled as a
shared shock — the backtest shows how much that matters.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

RACE_POINTS = [25, 18, 15, 12, 10, 8, 6, 4, 2, 1]
SPRINT_POINTS = [8, 7, 6, 5, 4, 3, 2, 1]
CB_LEN = 30  # countback positions tracked (P1..P30)

LIVE_SIMULATIONS = 10000
ODDS_SIMULATIONS = 20000
BACKTEST_SIMULATIONS = 2000
BETA_GRID = np.logspace(-2, 1.5, 141)

# Spread (in Plackett-Luce log-strength units) of each driver's season-long form shift. Without it
# every race is independent and a favourite wins the title in ~100% of runs from round 0 (e.g.
# 2024, when McLaren overtook Red Bull mid-season). Chosen by the championship backtest's log score
# over the finished seasons in the database (see backtest(form_sd=...)).
FORM_SHOCK_SD = 1.0


def fastest_lap_point(year: int) -> int:
    """A point for the fastest lap (if finishing in the top 10) from 2019 to 2024."""
    return 1 if 2019 <= year <= 2024 else 0


def max_round_points(sprint: bool, year: int, team: bool = False) -> int:
    """Most one driver (or one team's two cars) can score in a round."""
    fl = fastest_lap_point(year)
    if team:
        return RACE_POINTS[0] + RACE_POINTS[1] + fl + ((SPRINT_POINTS[0] + SPRINT_POINTS[1]) if sprint else 0)
    return RACE_POINTS[0] + fl + (SPRINT_POINTS[0] if sprint else 0)


@dataclass
class Round:
    round: int
    name: str
    circuit: str
    sprint: bool


# ---------------------------------------------------------------------------
# Standings from stored results
# ---------------------------------------------------------------------------

def clean_results(results: pd.DataFrame) -> pd.DataFrame:
    """One row per driver per session: a stale duplicate (the same driver stored twice in one
    session, e.g. an old unclassified row) keeps its best position only."""
    if results.empty:
        return results
    df = results.copy()
    df["points"] = pd.to_numeric(df["points"], errors="coerce").fillna(0.0)
    df = df.dropna(subset=["driver_id", "position"])
    df = df.sort_values("position").drop_duplicates(["round", "session_type", "driver_id"], keep="first")
    return df


def season_table(results: pd.DataFrame, by: str) -> Dict[str, Dict[str, Any]]:
    """Points and countback per driver (by='driver_id') or team (by='constructor_id').
    Points include sprints; the countback counts Grand Prix finishes only."""
    table: Dict[str, Dict[str, Any]] = {}
    if results.empty:
        return table
    for key, rows in results.groupby(by):
        if not key:
            continue
        cb = np.zeros(CB_LEN, dtype=int)
        for pos in rows.loc[rows["session_type"] == "race", "position"]:
            if 1 <= int(pos) <= CB_LEN:
                cb[int(pos) - 1] += 1
        table[key] = {"points": float(rows["points"].sum()), "countback": cb}
    return table


def _order_key(entry: Dict[str, Any]) -> Tuple:
    return (entry["points"], tuple(entry["countback"]))


def title_status(table: Dict[str, Dict[str, Any]], remaining: Sequence[Round], year: int,
                 team: bool = False) -> Dict[str, Any]:
    """Exact status: who can still win, and whether the leader has clinched it.

    A contender is still alive if, scoring the maximum in every remaining round while the leader
    scores nothing, they'd finish ahead — on points, or level on points and ahead on countback
    (their best case adds a win per remaining race; a team's adds a one-two)."""
    if not table:
        return {"leader": None, "alive": {}, "clinched": False, "max_points_remaining": 0, "next_race_clinch": None}

    max_rem = sum(max_round_points(r.sprint, year, team) for r in remaining)
    ranked = sorted(table, key=lambda k: _order_key(table[k]), reverse=True)
    leader = ranked[0]
    lead = table[leader]

    def best_case(key: str) -> Tuple[float, Tuple]:
        cb = table[key]["countback"].copy()
        cb[0] += len(remaining)
        if team:
            cb[1] += len(remaining)
        return table[key]["points"] + max_rem, tuple(cb)

    alive = {k: (k == leader) or best_case(k) > _order_key(lead) for k in ranked}
    clinched = not any(alive[k] for k in ranked if k != leader)

    next_hint = None
    if not clinched and remaining and len(ranked) > 1:
        nxt = remaining[0]
        after = max_rem - max_round_points(nxt.sprint, year, team)
        rival = ranked[1]
        gap = lead["points"] - table[rival]["points"]
        # Clinch after the next round needs lead + margin > rival's points + everything left after it.
        needed = int(after - gap + 1)
        if needed <= max_round_points(nxt.sprint, year, team):
            next_hint = {"round": nxt.round, "race_name": nxt.name, "rival": rival, "margin_needed": needed}

    return {
        "leader": leader,
        "alive": alive,
        "clinched": clinched,
        "max_points_remaining": max_rem,
        "next_race_clinch": next_hint,
    }


# ---------------------------------------------------------------------------
# Plackett-Luce
# ---------------------------------------------------------------------------

def pl_log_likelihood(scores_in_finish_order: np.ndarray, beta: float) -> float:
    """log P(this exact finishing order) under Plackett-Luce with strengths exp(beta * score)."""
    s = beta * np.asarray(scores_in_finish_order, dtype=float)
    tail = np.logaddexp.accumulate(s[::-1])[::-1]  # log-sum-exp of everyone not yet placed
    return float(np.sum(s - tail))


def fit_beta(races: Sequence[np.ndarray]) -> float:
    """Most likely beta for races given as score arrays sorted by actual finishing order."""
    races = [r for r in races if len(r) >= 2]
    if not races:
        return 1.0
    ll = [sum(pl_log_likelihood(r, b) for r in races) for b in BETA_GRID]
    best = float(BETA_GRID[int(np.argmax(ll))])
    if best in (BETA_GRID[0], BETA_GRID[-1]):
        logger.warning("championship: beta fit hit the edge of its search range (%.3f)", best)
    return best


def sample_orders(scores: np.ndarray, beta: float, n_sims: int, rng: np.random.Generator,
                  offset: Optional[np.ndarray] = None) -> np.ndarray:
    """(n_sims, n) finishing positions (0 = winner) drawn from Plackett-Luce via Gumbel noise.
    `offset` (n_sims, n) shifts each simulated season's strengths (see FORM_SHOCK_SD)."""
    u = beta * scores[None, :] + rng.gumbel(size=(n_sims, len(scores)))
    if offset is not None:
        u = u + offset
    order = np.argsort(-u, axis=1)
    pos = np.empty_like(order)
    np.put_along_axis(pos, order, np.arange(len(scores))[None, :].repeat(n_sims, 0), axis=1)
    return pos


def _points_lookup(table: List[int], n: int) -> np.ndarray:
    out = np.zeros(max(n, len(table)), dtype=float)
    out[: len(table)] = table
    return out


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------

def simulate_season(
    driver_table: Dict[str, Dict[str, Any]],
    team_table: Dict[str, Dict[str, Any]],
    entrants: List[str],
    team_of: Dict[str, str],
    round_scores: List[Tuple[np.ndarray, bool]],
    beta: float,
    n_sims: int,
    rng: np.random.Generator,
    form_sd: float = 0.0,
) -> Dict[str, Dict[str, Any]]:
    """Play out the remaining rounds n_sims times.

    round_scores: per remaining round, (race scores aligned to `entrants`, is_sprint_weekend).
    Returns {"drivers": {id: stats}, "teams": {id: stats}} with expected points, title probability
    and the probability of every final position."""
    drivers = sorted(set(driver_table) | set(entrants))
    teams = sorted(set(team_table) | {team_of[d] for d in entrants if team_of.get(d)})
    d_idx = {d: i for i, d in enumerate(drivers)}
    t_idx = {t: i for i, t in enumerate(teams)}

    def start(table: Dict[str, Dict[str, Any]], ids: List[str]) -> np.ndarray:
        # Points plus a countback tie-break folded into tiny fractions (wins * 1e-3, P2s * 1e-6, ...).
        base = np.zeros(len(ids))
        for i, k in enumerate(ids):
            if k in table:
                cb = table[k]["countback"]
                base[i] = table[k]["points"] + sum(cb[j] * 10.0 ** (-3 * (j + 1)) for j in range(4))
        return base

    d_tot = np.tile(start(driver_table, drivers), (n_sims, 1))
    t_tot = np.tile(start(team_table, teams), (n_sims, 1))
    d_pts = np.tile([driver_table.get(d, {}).get("points", 0.0) for d in drivers], (n_sims, 1))
    t_pts = np.tile([team_table.get(t, {}).get("points", 0.0) for t in teams], (n_sims, 1))

    n = len(entrants)
    e_cols = np.array([d_idx[d] for d in entrants], dtype=int)
    team_matrix = np.zeros((n, len(teams)))
    for i, d in enumerate(entrants):
        if team_of.get(d) in t_idx:
            team_matrix[i, t_idx[team_of[d]]] = 1.0
    race_pts = _points_lookup(RACE_POINTS, n)
    sprint_pts = _points_lookup(SPRINT_POINTS, n)
    tiebreak = np.zeros(n)
    tiebreak[:min(4, n)] = [10.0 ** (-3 * (j + 1)) for j in range(min(4, n))]

    # Form that lasts: in each simulated season every driver is a bit quicker or slower than the
    # model says for all the remaining rounds, not independently race by race.
    shock = rng.normal(0.0, form_sd, size=(n_sims, n)) if form_sd > 0 else None

    for scores, sprint in round_scores:
        pos = sample_orders(scores, beta, n_sims, rng, shock)
        gained = race_pts[pos]
        tb = tiebreak[pos]  # countback: Grand Prix finishes only
        if sprint:
            gained = gained + sprint_pts[sample_orders(scores, beta, n_sims, rng, shock)]
        d_pts[:, e_cols] += gained
        d_tot[:, e_cols] += gained + tb
        t_pts += gained @ team_matrix
        t_tot += (gained + tb) @ team_matrix

    def summarise(tot: np.ndarray, pts: np.ndarray, ids: List[str]) -> Dict[str, Dict[str, Any]]:
        order = np.argsort(-tot, axis=1)
        rank = np.empty_like(order)
        np.put_along_axis(rank, order, np.arange(len(ids))[None, :].repeat(len(tot), 0), axis=1)
        out = {}
        for i, k in enumerate(ids):
            probs = np.bincount(rank[:, i], minlength=len(ids)) / len(tot)
            out[k] = {
                "projected_points": float(pts[:, i].mean()),
                "points_p10": float(np.percentile(pts[:, i], 10)),
                "points_p90": float(np.percentile(pts[:, i], 90)),
                "title_probability": float(probs[0]),
                "position_probabilities": [round(float(p), 4) for p in probs],
            }
        return out

    return {"drivers": summarise(d_tot, d_pts, drivers), "teams": summarise(t_tot, t_pts, teams)}


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class ChampionshipService:
    def __init__(self, prediction_service, seed: Optional[int] = None):
        self.pred = prediction_service
        self.seed = seed
        self.form_sd = FORM_SHOCK_SD
        self._held_out: Optional[Dict[str, Any]] = None  # per-season models + held-out race scores
        self._cache: Dict[Tuple, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    # ---- models trained only on earlier seasons ------------------------------------------

    def _season_models(self, lgb, year: int):
        p = self.pred
        train = p._df[p._df["year"] < year]
        if train.empty:
            return None, None
        return (p._fit_ranker(lgb, train, p._quali_features, "grid"),
                p._fit_ranker(lgb, train, p._race_features, "position"))

    def _score_rows(self, rows: pd.DataFrame, quali_model, race_model) -> np.ndarray:
        """Race scores for one race's feature rows, the way a future race is predicted: the grid
        input is the qualifying model's predicted rank and there's no practice pace yet."""
        p = self.pred
        rows = rows.copy()
        rows["driver_practice_best_rank"] = np.nan
        if quali_model is not None:
            rows["grid"] = p._ranks_from_scores(quali_model.predict(rows[p._quali_features].astype(float).fillna(10)))
        return race_model.predict(rows[p._race_features].astype(float).fillna(10))

    def _build_held_out(self) -> Dict[str, Any]:
        """For every season with earlier data to learn from: a model trained only on the seasons
        before it, and its scores for that season's races (sorted by actual finish)."""
        import lightgbm as lgb

        p = self.pred
        df = p._df
        years = sorted(int(y) for y in df["year"].unique())
        models: Dict[int, Tuple[Any, Any]] = {}
        races: Dict[int, List[np.ndarray]] = {}
        qualifyings: List[np.ndarray] = []
        for year in years[1:]:
            quali_model, race_model = self._season_models(lgb, year)
            if race_model is None:
                continue
            models[year] = (quali_model, race_model)
            season = df[(df["year"] == year) & df["position"].notna()]
            races[year] = []
            for _, rows in season.groupby("race_id"):
                rows = rows.sort_values("position")
                races[year].append(np.asarray(self._score_rows(rows, quali_model, race_model)))
                graded = rows.dropna(subset=["grid"]).sort_values("grid")
                if quali_model is not None and len(graded) >= 2:
                    graded = graded.assign(driver_practice_best_rank=np.nan)
                    qualifyings.append(np.asarray(quali_model.predict(graded[p._quali_features].astype(float).fillna(10))))
        all_races = [r for rs in races.values() for r in rs]
        return {
            "fingerprint": (p._meta.get("trained_at"), len(df)),
            "models": models,
            "races": races,
            "beta": fit_beta(all_races),
            "races_used": len(all_races),
            "beta_qualifying": fit_beta(qualifyings) if qualifyings else None,
        }

    def _held_out_state(self) -> Dict[str, Any]:
        fp = (self.pred._meta.get("trained_at"), len(self.pred._df))
        if self._held_out is None or self._held_out["fingerprint"] != fp:
            self._held_out = self._build_held_out()
            logger.info("championship: beta=%.3f from %d held-out races",
                        self._held_out["beta"], self._held_out["races_used"])
        return self._held_out

    # ---- odds for one upcoming session (the Predictions page) -----------------------------

    def odds_ready(self) -> bool:
        p = self.pred
        return (self._held_out is not None and p._df is not None
                and self._held_out["fingerprint"] == (p._meta.get("trained_at"), len(p._df)))

    async def warm(self) -> None:
        """Build the held-out calibration in the background (a few model fits)."""
        if self.odds_ready() or self.pred._df is None:
            return
        async with self._lock:
            if not self.odds_ready():
                await asyncio.to_thread(self._held_out_state)

    def with_finish_odds(self, result: Dict[str, Any], kind: str) -> Dict[str, Any]:
        """Add expected position and win/podium chances to a race or qualifying prediction,
        by playing the session out with the same calibrated Plackett-Luce model as the title
        outlook. Expected position follows the predicted order (a higher score is always a
        better expected finish), so it can sit next to the rank without contradicting it.
        Needs the calibration (warm()); without it the result is returned unchanged."""
        preds = result.get("predictions") or []
        if kind not in ("race", "qualifying") or not preds or any("score" not in r for r in preds) or not self.odds_ready():
            return {**result, "odds_available": False}
        beta = self._held_out["beta"] if kind == "race" else self._held_out.get("beta_qualifying")
        if not beta:
            return {**result, "odds_available": False}
        scores = np.array([float(r["score"]) for r in preds])
        pos = sample_orders(scores, beta, ODDS_SIMULATIONS, np.random.default_rng(0))
        stats = {
            "expected_position": pos.mean(axis=0) + 1,
            "win_probability": (pos == 0).mean(axis=0),
            "podium_probability": (pos < 3).mean(axis=0),
        }
        if kind == "race":
            stats["points_probability"] = (pos < 10).mean(axis=0)
        # Under Plackett-Luce a higher score is always at least as good on every one of these,
        # so drivers with near-equal scores can only swap through sampling noise: put the
        # estimates back in score order.
        by_score = np.argsort(-scores, kind="stable")
        for key, values in stats.items():
            ordered = np.sort(values) if key == "expected_position" else np.sort(values)[::-1]
            fixed = np.empty_like(values)
            fixed[by_score] = ordered
            stats[key] = fixed
        enriched = []
        for i, r in enumerate(preds):
            extra = {k: round(float(v[i]), 1 if k == "expected_position" else 4) for k, v in stats.items()}
            enriched.append({**r, **extra})
        return {**result, "predictions": enriched, "odds_available": True}

    # ---- scores for the rounds still to run ----------------------------------------------

    def _round_scores(self, remaining: List[Round], entrants: List[str], team_of: Dict[str, str],
                      history: pd.DataFrame, quali_model, race_model) -> List[Tuple[np.ndarray, bool]]:
        p = self.pred
        out = []
        cache: Dict[str, np.ndarray] = {}
        team_form = history.sort_values(["year", "round"]).groupby("constructor_id")["constructor_rolling_finish"].last()
        for rnd in remaining:
            if rnd.circuit not in cache:
                rows = p._build_prediction_rows(rnd.circuit, history)
                # A driver who changed teams races the new car: use the team they drive for now,
                # not the one in their last history row (Sainz at Williams in 2025, not Ferrari).
                for i, row in rows.iterrows():
                    team = team_of.get(row["driver_id"])
                    if team and team != row["constructor_id"]:
                        at_circuit = history.loc[(history["constructor_id"] == team)
                                                 & (history["circuit_name"] == rnd.circuit), "position"]
                        form = team_form.get(team, np.nan)
                        rows.at[i, "constructor_id"] = team
                        rows.at[i, "constructor_rolling_finish"] = form
                        rows.at[i, "constructor_circuit_avg"] = at_circuit.mean() if not at_circuit.empty else form
                rows = p._encode(rows)
                rows = rows.set_index("driver_id").reindex(entrants)
                # A driver with no history (a debut) gets the field's median inputs.
                rows = rows.fillna(rows.median(numeric_only=True)).reset_index()
                cache[rnd.circuit] = np.asarray(self._score_rows(rows, quali_model, race_model), dtype=float)
            out.append((cache[rnd.circuit], rnd.sprint))
        return out

    # ---- one season at one point in time -------------------------------------------------

    def _project(self, year: int, results: pd.DataFrame, rounds: List[Round], completed: int,
                 history: pd.DataFrame, quali_model, race_model, beta: float, n_sims: int,
                 rng: np.random.Generator, form_sd: Optional[float] = None) -> Dict[str, Any]:
        done = results[results["round"] <= completed]
        driver_table = season_table(done, "driver_id")
        team_table = season_table(done, "constructor_id")
        remaining = [r for r in rounds if r.round > completed]

        # Who races the rest of the season: the field of the latest round run (the first
        # round's field before the season starts).
        field_round = completed if completed > 0 else (min(results["round"]) if not results.empty else None)
        field = results[(results["round"] == field_round) & (results["session_type"] == "race")] if field_round else results.iloc[0:0]
        if field.empty and not history.empty:  # pre-season with nothing stored yet: last season's grid
            last = history[history["year"] == history["year"].max()]
            field = last[last["round"] == last["round"].max()]
        entrants = sorted(field["driver_id"].dropna().unique().tolist())
        team_of = field.drop_duplicates("driver_id").set_index("driver_id")["constructor_id"].to_dict()

        # A driver who is no longer in the field can't score again, so can't still win it.
        driver_status = title_status(driver_table, remaining, year)
        if remaining and entrants:
            driver_status["alive"] = {k: v and (k in entrants or k == driver_status["leader"])
                                      for k, v in driver_status["alive"].items()}

        sims = None
        if remaining and entrants and race_model is not None:
            scores = self._round_scores(remaining, entrants, team_of, history, quali_model, race_model)
            sims = simulate_season(driver_table, team_table, entrants, team_of, scores, beta, n_sims, rng,
                                   self.form_sd if form_sd is None else form_sd)

        return {
            "remaining": remaining,
            "drivers": (driver_table, driver_status, sims["drivers"] if sims else None),
            "teams": (team_table, title_status(team_table, remaining, year, team=True), sims["teams"] if sims else None),
            "team_of": team_of,
        }

    # ---- public --------------------------------------------------------------------------

    async def outlook(self, year: int, db, sprint_rounds: Optional[Set[int]] = None) -> Dict[str, Any]:
        """Both championships for `year`, as of the latest stored results."""
        await self.pred._ensure_trained(db)
        results = clean_results(pd.DataFrame(await db.get_season_results(year)))
        races = await db.get_races_by_year(year)

        completed = int(results.loc[results["session_type"] == "race", "round"].max()) if not results.empty and (results["session_type"] == "race").any() else 0
        sprint_done = set(results.loc[results["session_type"] == "sprint", "round"].astype(int)) if not results.empty else set()
        rounds = [
            Round(int(r["round"]), str(r.get("gp") or ""), str(r.get("circuit_name") or ""),
                  int(r["round"]) in sprint_done or int(r["round"]) in (sprint_rounds or set()))
            for r in races
        ]

        # Keyed on the results' content, not their count: a post-race penalty re-ingest changes
        # positions and points without adding a row.
        content = pd.util.hash_pandas_object(results[["round", "session_type", "driver_id", "position", "points"]], index=False).sum() if not results.empty else 0
        key = (year, self.pred._meta.get("trained_at"), int(content), tuple(sorted(sprint_rounds or ())))
        if key in self._cache:
            return self._cache[key]

        async with self._lock:
            if key in self._cache:
                return self._cache[key]
            result = await asyncio.to_thread(self._outlook_sync, year, results, rounds, completed, sprint_rounds is not None)
            self._cache = {k: v for k, v in self._cache.items() if k[0] != year}  # keep one per season
            self._cache[key] = result
            return result

    def _outlook_sync(self, year: int, results: pd.DataFrame, rounds: List[Round], completed: int,
                      sprint_info: bool) -> Dict[str, Any]:
        held = self._held_out_state()
        p = self.pred
        rng = np.random.default_rng(self.seed)
        proj = self._project(year, results, rounds, completed, p._df, p._quali_model, p._race_model,
                             held["beta"], LIVE_SIMULATIONS, rng)

        names = results.drop_duplicates("driver_id").set_index("driver_id")["driver_name"].to_dict() if not results.empty else {}
        team_names = results.dropna(subset=["constructor_id"]).drop_duplicates("constructor_id").set_index("constructor_id")["constructor_name"].to_dict() if not results.empty else {}
        # The team each driver drove for most recently (a driver who left keeps their last one).
        last_team = results.sort_values("round").groupby("driver_id")["constructor_id"].last().to_dict() if not results.empty else {}
        remaining = proj["remaining"]
        status = "finished" if completed and not remaining else ("pre_season" if not completed else "in_progress")

        def build(kind: str) -> Dict[str, Any]:
            table, exact, sims = proj[kind]
            ids = sorted(set(table) | set(sims or {}), key=lambda k: _order_key(table.get(k, {"points": 0, "countback": np.zeros(CB_LEN, int)})), reverse=True)
            rows = []
            for pos, k in enumerate(ids, start=1):
                entry = table.get(k, {"points": 0.0, "countback": np.zeros(CB_LEN, int)})
                sim = (sims or {}).get(k)
                row = {
                    "id": k,
                    "code": k.upper() if kind == "drivers" else None,
                    "name": (names.get(k) if kind == "drivers" else team_names.get(k)) or k,
                    "team": team_names.get(last_team.get(k, ""), None) if kind == "drivers" else None,
                    "position": pos,
                    "points": entry["points"],
                    "wins": int(entry["countback"][0]),
                    "alive": bool(exact["alive"].get(k, False)),
                }
                if sim:
                    row.update(sim)
                else:  # decided: the table is final
                    row.update({"projected_points": entry["points"], "points_p10": entry["points"], "points_p90": entry["points"],
                                "title_probability": 1.0 if (pos == 1 and exact["clinched"]) else 0.0,
                                "position_probabilities": None})
                rows.append(row)
            # Projected order: expected points (title chance breaks ties).
            for i, r in enumerate(sorted(rows, key=lambda r: (-r["projected_points"], -r["title_probability"])), start=1):
                r["projected_position"] = i
            hint = exact["next_race_clinch"]
            if hint:
                hint = {**hint, "rival_name": (names.get(hint["rival"]) if kind == "drivers" else team_names.get(hint["rival"])) or hint["rival"]}
            leader = exact["leader"]
            return {
                "clinched": bool(exact["clinched"]) and bool(completed),
                "champion": ((names.get(leader) if kind == "drivers" else team_names.get(leader)) or leader) if exact["clinched"] and completed else None,
                "max_points_remaining": exact["max_points_remaining"],
                "next_race_clinch": hint,
                "standings": rows,
            }

        return {
            "year": year,
            "status": status,
            "rounds_completed": completed,
            "rounds_total": len(rounds),
            "remaining": [{"round": r.round, "name": r.name, "sprint": r.sprint} for r in remaining],
            "sprint_calendar_known": sprint_info,
            "drivers": build("drivers"),
            "constructors": build("teams"),
            "method": {
                "simulations": LIVE_SIMULATIONS if remaining else 0,
                "beta": round(held["beta"], 4),
                "calibration_races": held["races_used"],
                "model_trained_at": p._meta.get("trained_at"),
            },
            "computed_at": datetime.utcnow().isoformat(),
        }

    # ---- backtest ------------------------------------------------------------------------

    async def backtest(self, db, form_sd: Optional[float] = None) -> Dict[str, Any]:
        """Replay finished seasons round by round: at each point, would the projection have
        named the eventual champion, and how much probability did it give them? Each season uses
        models trained only on earlier seasons, and a beta fitted on the other seasons' races."""
        await self.pred._ensure_trained(db)
        seasons = {}
        current = datetime.utcnow().year
        for year in sorted(int(y) for y in self.pred._df["year"].unique()):
            if year >= current:
                continue
            seasons[year] = (clean_results(pd.DataFrame(await db.get_season_results(year))),
                             await db.get_races_by_year(year))
        return await asyncio.to_thread(self._backtest_sync, seasons, form_sd)

    def _backtest_sync(self, seasons: Dict[int, Tuple[pd.DataFrame, List[Dict]]],
                       form_sd: Optional[float] = None) -> Dict[str, Any]:
        form_sd = self.form_sd if form_sd is None else form_sd
        held = self._held_out_state()
        p = self.pred
        rng = np.random.default_rng(self.seed if self.seed is not None else 7)
        out_seasons = []
        for year, (results, races) in seasons.items():
            if year not in held["models"] or results.empty:
                continue
            quali_model, race_model = held["models"][year]
            others = [r for y, rs in held["races"].items() if y != year for r in rs]
            beta = fit_beta(others) if others else held["beta"]

            race_rounds = sorted(int(r) for r in results.loc[results["session_type"] == "race", "round"].unique())
            sprint_done = set(results.loc[results["session_type"] == "sprint", "round"].astype(int))
            rounds = [Round(int(r["round"]), str(r.get("gp") or ""), str(r.get("circuit_name") or ""), int(r["round"]) in sprint_done)
                      for r in races if int(r["round"]) in race_rounds]
            final = {kind: title_status(season_table(results, by), [], year, team=(kind == "teams"))["leader"]
                     for kind, by in (("drivers", "driver_id"), ("teams", "constructor_id"))}
            final_tables = {"drivers": season_table(results, "driver_id"), "teams": season_table(results, "constructor_id")}
            final_order = {kind: sorted(t, key=lambda k: _order_key(t[k]), reverse=True) for kind, t in final_tables.items()}

            points = []
            for completed in range(0, len(rounds)):
                history = p._df[(p._df["year"] < year) | ((p._df["year"] == year) & (p._df["round"] <= completed))]
                proj = self._project(year, results, rounds, completed, history, quali_model, race_model,
                                     beta, BACKTEST_SIMULATIONS, rng, form_sd)
                entry = {"round": completed}
                for kind in ("drivers", "teams"):
                    table, exact, sims = proj[kind]
                    if not sims:
                        continue
                    champ = final[kind]
                    predicted = max(sims, key=lambda k: sims[k]["title_probability"])
                    leader = exact["leader"]
                    brier = sum((s["title_probability"] - (1.0 if k == champ else 0.0)) ** 2 for k, s in sims.items())
                    projected = sorted(sims, key=lambda k: -sims[k]["projected_points"])
                    order_err = [abs(projected.index(k) - final_order[kind].index(k)) for k in projected if k in final_order[kind]]
                    entry[kind] = {
                        "predicted": predicted,
                        "p_actual_champion": round(sims.get(champ, {}).get("title_probability", 0.0), 4),
                        "correct": predicted == champ,
                        "leader_correct": leader == champ,
                        "brier": round(brier, 4),
                        "final_order_mae": round(float(np.mean(order_err)), 3) if order_err else None,
                    }
                points.append(entry)
            out_seasons.append({"year": year, "champion": final["drivers"], "constructors_champion": final["teams"],
                                "rounds": len(rounds), "beta": round(beta, 4), "points": points})

        def summary(kind: str) -> Dict[str, Any]:
            pts = [e[kind] for s in out_seasons for e in s["points"] if kind in e]
            if not pts:
                return {}
            return {
                "checkpoints": len(pts),
                "champion_accuracy": round(float(np.mean([e["correct"] for e in pts])), 3),
                "leader_accuracy": round(float(np.mean([e["leader_correct"] for e in pts])), 3),
                "mean_p_actual_champion": round(float(np.mean([e["p_actual_champion"] for e in pts])), 3),
                "brier": round(float(np.mean([e["brier"] for e in pts])), 4),
                # Mean log-probability given to the eventual champion (higher is better; floored
                # at 1e-3 so one confident miss can't dominate).
                "log_score": round(float(np.mean([np.log(max(e["p_actual_champion"], 1e-3)) for e in pts])), 3),
                "final_order_mae": round(float(np.mean([e["final_order_mae"] for e in pts if e["final_order_mae"] is not None])), 3),
            }

        return {
            "seasons": out_seasons,
            "drivers": summary("drivers"),
            "constructors": summary("teams"),
            "form_sd": form_sd,
            "computed_at": datetime.utcnow().isoformat(),
        }
