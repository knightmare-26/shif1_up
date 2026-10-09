"""
Same-weekend practice pace as model inputs (Phase 1, #30).

Every stored practice session has each driver's best lap (`race_results.time`, see
ingest_service._extract_practice_results); `position` there is the rank by that lap. The rank
throws away how far apart the cars are, so these features keep the gap:

- driver_practice_best_rank        best rank across FP1-3 (the original input)
- driver_practice_gap_pct          best lap vs the session's fastest, % — best across sessions
- team_practice_gap_pct            the team's quicker car, the same way
- driver_practice_teammate_gap_pct vs the teammate in the same session, % — median across sessions

Teams come from the weekend's race/qualifying rows where they exist (practice rows sometimes lack
one), else the practice row's own. A lap more than GAP_CAP % off the pace isn't a representative
lap (an installation run, a red flag) and is capped.
"""
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

PRACTICE_SESSIONS = ("fp1", "fp2", "fp3")
GAP_CAP = 5.0
COLUMNS = ["driver_practice_best_rank", "driver_practice_gap_pct",
           "team_practice_gap_pct", "driver_practice_teammate_gap_pct"]


def _lap_seconds(times: pd.Series) -> pd.Series:
    return pd.to_timedelta(times.astype("string").replace("", pd.NA), errors="coerce").dt.total_seconds()


def practice_features(raw: pd.DataFrame, teams: Optional[Dict[tuple, str]] = None) -> pd.DataFrame:
    """One row per (race_id, driver_id) that ran a practice session, with COLUMNS.
    `teams` ((race_id, driver_id) -> constructor_id) overrides the practice rows' teams."""
    practice = raw[raw["session_type"].isin(PRACTICE_SESSIONS)].copy()
    if practice.empty:
        return pd.DataFrame(columns=["race_id", "driver_id"] + COLUMNS)

    if teams is None:
        others = raw[raw["session_type"].isin(["race", "qualifying", "sprint"])].dropna(subset=["constructor_id"])
        others = others[others["constructor_id"] != ""]
        teams = dict(zip(zip(others["race_id"], others["driver_id"]), others["constructor_id"]))
    own = practice["constructor_id"].where(practice["constructor_id"].fillna("") != "", None)
    practice["team"] = [teams.get(k, o) for k, o in zip(zip(practice["race_id"], practice["driver_id"]), own)]

    out = practice.groupby(["race_id", "driver_id"])["position"].min().rename("driver_practice_best_rank").to_frame()

    if "time" in practice:
        practice["lap"] = _lap_seconds(practice["time"])
        timed = practice.dropna(subset=["lap"]).copy()
        if not timed.empty:
            session = ["race_id", "session_type"]
            fastest = timed.groupby(session)["lap"].transform("min")
            timed["gap"] = ((timed["lap"] / fastest - 1) * 100).clip(upper=GAP_CAP)

            out = out.join(timed.groupby(["race_id", "driver_id"])["gap"].min().rename("driver_practice_gap_pct"))

            with_team = timed.dropna(subset=["team"])
            team_best = with_team.groupby(session + ["team"])["gap"].min().rename("team_gap")
            per_team = team_best.groupby(["race_id", "team"]).min().rename("team_practice_gap_pct").reset_index()
            driver_team = (with_team.sort_values("session_type").drop_duplicates(["race_id", "driver_id"], keep="last")
                           [["race_id", "driver_id", "team"]])
            team_col = driver_team.merge(per_team, on=["race_id", "team"], how="left").set_index(["race_id", "driver_id"])
            out = out.join(team_col["team_practice_gap_pct"])

            # Teammate: the driver's gap minus the best other car of the team in that session.
            if not with_team.empty:
                cars = with_team.groupby(session + ["team"])["gap"]
                best = cars.transform("min")
                second = cars.transform(lambda g: g.nsmallest(2).iloc[-1] if len(g) > 1 else np.nan)
                other = np.where(with_team["gap"] == best, second, best)
                with_team = with_team.assign(mate=(with_team["gap"] - other).where(cars.transform("count") > 1))
                out = out.join(with_team.groupby(["race_id", "driver_id"])["mate"].median()
                               .rename("driver_practice_teammate_gap_pct"))

    for col in COLUMNS:
        if col not in out:
            out[col] = np.nan
    return out[COLUMNS].reset_index()


def select(columns: List[str], available: bool) -> List[str]:
    """The practice inputs a model uses: none until most training rows have practice."""
    return list(columns) if available else []
