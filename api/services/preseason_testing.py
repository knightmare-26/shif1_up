"""
Preseason testing as the first evidence about a season's cars (Phase 3b, #35).

In a stable season the first races are predicted about as well as the rest; in the first season of
new rules they're much worse — 2026 qualifying was off by 4.38 places in races 1-3 against 2.34
from race 7 — because last season's form says little about the new cars, and testing is the only
evidence before round 1.

Each season's testing is summarised per driver — best lap over all testing days, the compound it
was set on, laps run — and stored in `prediction_cache` (circuit_name `_testing`, session_type
the year; kept by clear_prediction_cache()). OpenF1 has it from 2023 (free; 2026 had two tests),
FastF1 for earlier seasons (scripts/backfill_testing.py). Teams are grouped by the name they ran
under in testing, so a new team needs no mapping onto our constructor ids.

Testing times are noisy — fuel loads, programmes, tyres, sandbagging — so the features are gaps to
the fastest (%) and they fade out over the first races (see `testing_features`).
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from services.openf1_live import OpenF1Client, parse_time

logger = logging.getLogger(__name__)

# Seasons that started a new set of technical rules.
ERA_STARTS = {2014, 2017, 2022, 2026}
CACHE_KEY = "_testing"
GAP_CAP = 5.0                 # % — a car that never ran a quick lap isn't 8% slower
COLUMNS = ["driver_testing_gap_pct", "team_testing_gap_pct"]


def summarise(laps: List[Dict[str, Any]], year: int, source: str, sessions: int) -> Optional[Dict[str, Any]]:
    """laps: {driver_id, team, seconds, compound}. Best lap per driver over all of testing."""
    drivers: Dict[str, Dict[str, Any]] = {}
    for lap in laps:
        d = drivers.setdefault(lap["driver_id"], {"driver_id": lap["driver_id"], "team": lap.get("team") or "",
                                                  "best_lap": None, "best_lap_compound": None, "laps": 0})
        d["laps"] += 1
        if lap.get("team"):
            d["team"] = lap["team"]
        if lap.get("seconds") and (d["best_lap"] is None or lap["seconds"] < d["best_lap"]):
            d["best_lap"], d["best_lap_compound"] = round(float(lap["seconds"]), 3), lap.get("compound")
    rows = [d for d in drivers.values() if d["best_lap"]]
    if len(rows) < 10:
        return None
    return {"year": year, "source": source, "sessions": sessions, "drivers": sorted(rows, key=lambda d: d["best_lap"])}


async def finished_sessions(client: OpenF1Client, year: int, now: datetime) -> List[Dict[str, Any]]:
    meetings = [m for m in await client.get("meetings", year=year)
                if "test" in (m.get("meeting_name") or "").lower() and not m.get("is_cancelled")]
    out = []
    for meeting in meetings:
        for session in await client.get("sessions", meeting_key=meeting["meeting_key"]):
            ended = parse_time(session.get("date_end"))
            if ended is not None and ended <= now:
                out.append(session)
    return out


async def from_openf1(client: OpenF1Client, year: int, now: Optional[datetime] = None,
                      sessions_list: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
    """The season's finished testing days from OpenF1, or None if there's no testing yet."""
    now = now or datetime.now(timezone.utc)
    laps: List[Dict[str, Any]] = []
    sessions = 0
    for session in sessions_list if sessions_list is not None else await finished_sessions(client, year, now):
        key = session["session_key"]
        drivers = {d.get("driver_number"): d for d in await client.get("drivers", session_key=key)}
        stints = await client.get("stints", session_key=key)
        sessions += 1
        for lap in await client.get("laps", session_key=key):
            info = drivers.get(lap.get("driver_number")) or {}
            code = (info.get("name_acronym") or "").lower()
            if not code or lap.get("is_pit_out_lap"):
                continue
            n = lap.get("lap_number") or 0
            compound = next((s.get("compound") for s in stints if s.get("driver_number") == lap.get("driver_number")
                             and (s.get("lap_start") or 0) <= n <= (s.get("lap_end") or 10 ** 6)), None)
            laps.append({"driver_id": code, "team": info.get("team_name"), "seconds": lap.get("lap_duration"),
                         "compound": compound})
    return summarise(laps, year, "openf1", sessions) if sessions else None


def from_fastf1(year: int) -> Optional[Dict[str, Any]]:
    """Earlier seasons from FastF1 (slow; scripts only). FastF1 numbers tests per season and days
    per test; a test without public timing (2022 Barcelona) is skipped."""
    import fastf1
    laps: List[Dict[str, Any]] = []
    sessions = 0
    for test in (1, 2, 3):
        for day in (1, 2, 3, 4):
            try:
                s = fastf1.get_testing_session(year, test, day)
                s.load(laps=True, telemetry=False, weather=False, messages=False)
                frame = s.laps
            except Exception:
                continue
            frame = frame[frame["PitOutTime"].isna()] if "PitOutTime" in frame else frame
            sessions += 1
            for _, lap in frame.dropna(subset=["LapTime"]).iterrows():
                laps.append({"driver_id": str(lap["Driver"]).lower(), "team": lap.get("Team"),
                             "seconds": lap["LapTime"].total_seconds(), "compound": lap.get("Compound")})
    return summarise(laps, year, "fastf1", sessions) if sessions else None


async def load_stored(db, years) -> Dict[int, Dict[str, Any]]:
    out = {}
    for year in years:
        try:
            cached = await db.get_prediction_cache(CACHE_KEY, str(int(year)))
        except Exception:
            cached = None
        if cached and cached.get("result", {}).get("drivers"):
            out[int(year)] = cached["result"]
    return out


async def store(db, testing: Dict[str, Any]) -> None:
    await db.set_prediction_cache(CACHE_KEY, str(testing["year"]), testing["source"], testing)


def gaps(testing_by_year: Dict[int, Dict[str, Any]]) -> pd.DataFrame:
    """(year, driver_id, driver_testing_gap_pct, team_testing_gap_pct): best lap vs the fastest of
    that testing (%, capped), and the team's quicker car."""
    rows = []
    for year, testing in testing_by_year.items():
        drivers = pd.DataFrame(testing["drivers"])
        if drivers.empty:
            continue
        gap = ((drivers["best_lap"] / drivers["best_lap"].min() - 1) * 100).clip(upper=GAP_CAP)
        drivers = drivers.assign(year=int(year), driver_testing_gap_pct=gap)
        drivers["team_testing_gap_pct"] = drivers.groupby("team")["driver_testing_gap_pct"].transform("min")
        rows.append(drivers[["year", "driver_id"] + COLUMNS])
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["year", "driver_id"] + COLUMNS)


# ---------------------------------------------------------------------------------------------
# Using it
# ---------------------------------------------------------------------------------------------

# Inputs carrying last season's order into a new one — what a new era makes stale.
FORM_FEATURES = ["driver_rolling_grid", "driver_season_avg_grid", "driver_rolling_finish", "driver_circuit_avg",
                 "driver_circuit_grid_avg", "constructor_rolling_finish", "constructor_circuit_avg"]


def season_race_no(df: pd.DataFrame) -> pd.Series:
    """1 for a season's first race, 2 for its second, ..."""
    return df.groupby("year")["round"].rank(method="dense").astype(int)


def testing_weight(year: pd.Series, race_no: pd.Series, races: int, era_only: bool) -> np.ndarray:
    """1 at a season's first race, fading linearly to 0 after `races` races; 0 outside era starts if
    `era_only`."""
    w = np.clip(1 - (race_no.to_numpy() - 1) / max(races, 1), 0, 1)
    if era_only:
        w = np.where(year.isin(ERA_STARTS).to_numpy(), w, 0.0)
    return w


def implied_order(df: pd.DataFrame) -> pd.Series:
    """Each race's drivers ranked by their team's testing pace, then their own (1 = fastest). A driver
    who didn't test takes their team-mate's team gap; a team that didn't test goes last."""
    team_gap = df.groupby(["race_id", "constructor_id"])["team_testing_gap_pct"].transform("min").fillna(GAP_CAP + 1)
    own = df["driver_testing_gap_pct"].fillna(team_gap)
    keyed = df.assign(_t=team_gap, _o=own).sort_values(["race_id", "_t", "_o"])
    return keyed.groupby("race_id").cumcount().add(1).reindex(df.index).astype(float)


def apply_testing(df: pd.DataFrame, testing_by_year: Dict[int, Dict[str, Any]], mode: str, races: int) -> pd.DataFrame:
    """Add the testing inputs to engineered race rows.

    mode "off": nothing. "features" / "features_era": the gaps as model inputs, fading to neutral (the
    season's median) over the first `races` races — every season / era starts only. "rule": in an
    era-start season, the form inputs start from the testing order and blend into the real ones over
    the first `races` races (the model already knows how to use them; nothing new to learn from the
    two era starts there are)."""
    df = df.copy()
    df["season_race_no"] = season_race_no(df)
    if mode == "off" or not testing_by_year:
        return df
    df = df.drop(columns=COLUMNS, errors="ignore").merge(gaps(testing_by_year), on=["year", "driver_id"], how="left")
    if mode in ("features", "features_era"):
        w = testing_weight(df["year"], df["season_race_no"], races, era_only=mode == "features_era")
        for col in COLUMNS:
            neutral = df.groupby("year")[col].transform("median").fillna(1.0)
            df[col] = (neutral + w * (df[col] - neutral)).fillna(neutral)
    elif mode == "rule":
        w = testing_weight(df["year"], df["season_race_no"], races, era_only=True)
        has = df.groupby("race_id")["team_testing_gap_pct"].transform("count") > 0
        w = np.where(has.to_numpy(), w, 0.0)
        implied = implied_order(df)
        team_implied = implied.groupby([df["race_id"], df["constructor_id"]]).transform("mean")
        for col in FORM_FEATURES:
            if col not in df:
                continue
            target = team_implied if col.startswith("constructor") else implied
            df[col] = np.where(w > 0, w * target + (1 - w) * df[col].fillna(target), df[col])
        df = df.drop(columns=COLUMNS)
    return df


def apply_to_upcoming(rows: pd.DataFrame, testing_by_year: Dict[int, Dict[str, Any]], season: int,
                      race_no: int, races: int) -> pd.DataFrame:
    """The rule for a race still to come (one row per entered driver): in the first `races` races of
    an era-start season, the form inputs start from the testing order."""
    if season not in ERA_STARTS or season not in testing_by_year or rows.empty:
        return rows
    w = float(np.clip(1 - (race_no - 1) / max(races, 1), 0, 1))
    if w <= 0:
        return rows
    g = gaps({season: testing_by_year[season]}).drop(columns="year")
    df = rows.drop(columns=COLUMNS, errors="ignore").merge(g, on="driver_id", how="left").assign(race_id="next")
    implied = implied_order(df)
    team_implied = implied.groupby(df["constructor_id"]).transform("mean")
    for col in FORM_FEATURES:
        if col in df:
            target = team_implied if col.startswith("constructor") else implied
            df[col] = w * target + (1 - w) * df[col].fillna(target)
    return df.drop(columns=COLUMNS + ["race_id"])


async def refresh(db, client: OpenF1Client, year: int, first_race: Optional[str], now: Optional[datetime] = None) -> bool:
    """Store (or update) this season's testing from OpenF1 while it can still change — between
    1 February and the first race. Returns whether anything new was stored."""
    now = now or datetime.now(timezone.utc)
    if now.month < 2 or (first_race and now.date().isoformat() > first_race):
        return False
    stored = await load_stored(db, [year])
    finished = await finished_sessions(client, year, now)
    if len(finished) <= stored.get(year, {}).get("sessions", 0):
        return False                              # nothing new since last time: don't fetch the laps
    testing = await from_openf1(client, year, now, finished)
    if not testing:
        return False
    await store(db, testing)
    logger.info("preseason testing %s: stored %d sessions, %d drivers", year, testing["sessions"], len(testing["drivers"]))
    return True
