"""
Season-to-date form (Phase 2, #31).

Ranking drivers by championship points alone beat the qualifying model on position error (3.59 vs
3.77 places), so the model wasn't using what the season so far says. Per race, everything strictly
before it within its season:

- driver_season_avg_grid   the driver's average starting position so far this season (the first
                           race of a season: last season's final average)
- driver_season_points     the driver's Grand Prix points so far this season
- team_season_points       both cars' points so far this season

`*_after` columns include the race itself — what the *next* race is predicted from.
Walk-forward: qualifying 3.80 -> 3.63 places off with the average grid (paired t = -3.3); the points
barely move the race error but improve its win probabilities.
"""
import numpy as np
import pandas as pd

QUALI_INPUTS = ["driver_season_avg_grid"]
RACE_INPUTS = ["driver_season_points", "team_season_points"]


def add_season_form(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["year", "round"]).copy()
    points = df["points"].fillna(0).astype(float) if "points" in df else pd.Series(0.0, index=df.index)
    season = ["year", "driver_id"]

    df["driver_season_points_after"] = points.groupby([df["year"], df["driver_id"]]).cumsum()
    df["driver_season_points"] = df["driver_season_points_after"] - points

    team = (df.assign(_points=points)
              .groupby(["year", "round", "constructor_id"], dropna=False)["_points"].sum()
              .rename("_team").reset_index().sort_values(["year", "round"]))
    team["team_season_points_after"] = team.groupby(["year", "constructor_id"], dropna=False)["_team"].cumsum()
    team["team_season_points"] = team["team_season_points_after"] - team["_team"]
    df = df.merge(team[["year", "round", "constructor_id", "team_season_points", "team_season_points_after"]],
                  on=["year", "round", "constructor_id"], how="left")

    df["driver_season_avg_grid_after"] = df.groupby(season)["grid"].transform(lambda s: s.expanding().mean())
    df["driver_season_avg_grid"] = df.groupby(season)["driver_season_avg_grid_after"].shift(1)
    final = (df.groupby(season)["driver_season_avg_grid_after"].last().rename("_previous").reset_index()
               .assign(year=lambda d: d["year"] + 1))
    df = df.merge(final, on=season, how="left")
    fallback = df["driver_rolling_grid"] if "driver_rolling_grid" in df else np.nan
    df["driver_season_avg_grid"] = df["driver_season_avg_grid"].fillna(df["_previous"]).fillna(fallback)
    return df.drop(columns="_previous")


def team_points_after(history: pd.DataFrame, year: int) -> pd.Series:
    """Each team's season points after the latest race of `year` in `history`."""
    season = history[history["year"] == year]
    if season.empty or "team_season_points_after" not in season:
        return pd.Series(dtype=float)
    return season.sort_values("round").groupby("constructor_id")["team_season_points_after"].last()
