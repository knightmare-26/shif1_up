"""
The timing-board state shared by every live source (FastF1 poller, OpenF1 relay): session codes,
race ids, and the per-driver rows (best lap, sectors and their colours, tyres, stints, pit) built
from a FastF1-shaped laps table — Driver, LapNumber, LapTime, Sector1-3Time, Compound, TyreLife,
Stint, PitInTime, Position. A source only has to produce that table.
"""
from typing import Any, Dict, List, Optional

import pandas as pd

# FastF1 session codes the poller can follow. R and S are classified (race
# position, lap counter); the rest are timed — ranked by best lap, with no
# meaningful lap counter or classification to wait for.
SESSIONS = ("FP1", "FP2", "FP3", "SQ", "S", "Q", "R")
TIMED_SESSIONS = frozenset({"FP1", "FP2", "FP3", "SQ", "Q"})

# Timed sessions have no leader "Status" to key the end off, so they end once
# no lap has been completed for this long — generous enough to ride out a red
# flag. Ingest is an idempotent upsert, so ending early can't lose data.
TIMED_SESSION_END_STALL_SECONDS = 300


def is_timed_session(session: str) -> bool:
    return session in TIMED_SESSIONS


def build_race_id(year: int, gp: str, session: str = "R") -> str:
    """Must match the frontend's id convention (LiveDataMonitor.tsx): spaces ->
    underscores, slashes -> hyphens. The race keeps the bare `{year}_{gp}` id
    (LiveAnalytics and existing clients rely on it); other sessions get a suffix."""
    base = f"{year}_{gp.replace(' ', '_').replace('/', '-')}"
    return base if session == "R" else f"{base}_{session}"


def _format_lap_time(td) -> Optional[str]:
    if td is None or pd.isna(td):
        return None
    total_ms = int(round(td.total_seconds() * 1000))
    minutes, rest = divmod(total_ms, 60_000)
    return f"{minutes}:{rest / 1000:06.3f}"


def _format_sector(td) -> Optional[str]:
    if td is None or pd.isna(td):
        return None
    seconds = td.total_seconds()
    return f"{seconds:.3f}" if seconds < 60 else _format_lap_time(td)


def sector_status(value, driver_best, session_best) -> str:
    """Timing-screen colours for one sector of a driver's latest lap: purple = fastest
    of the session, green = the driver's own best, yellow = slower, none = not set."""
    if value is None or pd.isna(value):
        return "none"
    if session_best is not None and value == session_best:
        return "purple"
    if driver_best is not None and value == driver_best:
        return "green"
    return "yellow"


_SECTOR_COLUMNS = ("Sector1Time", "Sector2Time", "Sector3Time")


def _col(frame: pd.DataFrame, name: str):
    return frame[name] if name in frame.columns else pd.Series([pd.NaT] * len(frame), index=frame.index)


def build_driver_rows(laps: pd.DataFrame, teams: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    """One row per driver with everything the timing board shows (best lap and its colour,
    latest-lap sectors and their colours, tyre and its age, stint history, in-pit flag).
    Unordered and without position/gap — the caller orders them, since that is the only
    thing that differs between a timed session (best lap) and a classified one (race position)."""
    teams = teams or {}
    session_fastest = laps["LapTime"].dropna().min() if "LapTime" in laps else None
    session_sector_best = [_col(laps, c).dropna().min() if _col(laps, c).notna().any() else None for c in _SECTOR_COLUMNS]

    rows = []
    for driver, group in laps.groupby("Driver"):
        group = group.sort_values("LapNumber")
        last = group.iloc[-1]
        timed = group["LapTime"].dropna()
        best = timed.min() if not timed.empty else None

        sectors = []
        for column, session_best in zip(_SECTOR_COLUMNS, session_sector_best):
            personal = _col(group, column).dropna()
            value = last.get(column)
            sectors.append({
                "time": _format_sector(value),
                "status": sector_status(value, personal.min() if not personal.empty else None, session_best),
            })

        stints = []
        if "Stint" in group.columns and group["Stint"].notna().any():
            for _, stint in group.dropna(subset=["Stint"]).groupby("Stint", sort=True):
                compound = stint["Compound"].dropna()
                stints.append({"compound": compound.iloc[0] if not compound.empty else None, "laps": int(len(stint))})

        tyre_life = last.get("TyreLife")
        rows.append({
            "driver_id": driver,
            "driver_name": driver,
            "team": teams.get(driver),
            "best": best,
            "best_lap_time": _format_lap_time(best),
            "best_lap_status": None if best is None else ("purple" if best == session_fastest else "green"),
            "last": last.get("LapTime"),
            "last_lap_time": _format_lap_time(last.get("LapTime")),
            "laps_completed": int(group["LapNumber"].count()),
            "tyre": last.get("Compound") if pd.notna(last.get("Compound")) else None,
            "tyre_age": int(tyre_life) if pd.notna(tyre_life) else None,
            "stints": stints,
            "in_pit": bool(pd.notna(last.get("PitInTime"))),
            "sectors": sectors,
            "position_hint": last.get("Position"),
        })
    return rows


def _finish_rows(ordered: List[Dict[str, Any]], gaps: List[Optional[str]]) -> List[Dict[str, Any]]:
    positions = []
    for index, (r, gap) in enumerate(zip(ordered, gaps)):
        row = {k: v for k, v in r.items() if k not in ("best", "last", "position_hint")}
        row.update({
            "position": index + 1,
            "gap": gap,
            "interval": None,
            "status": "Running" if r["best"] is not None else "No time",
        })
        positions.append(row)
    return positions


def build_timed_positions(laps: pd.DataFrame, teams: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    """Practice / qualifying: drivers ordered by best lap so far, gap to the fastest.
    Drivers with no timed lap yet are listed last (status "No time") rather than dropped."""
    rows = build_driver_rows(laps, teams)
    rows.sort(key=lambda r: (r["best"] is None, r["best"] if r["best"] is not None else pd.Timedelta(0), r["driver_id"]))
    fastest = next((r["best"] for r in rows if r["best"] is not None), None)
    gaps = [
        f"+{(r['best'] - fastest).total_seconds():.3f}" if r["best"] is not None and fastest is not None and i > 0 else None
        for i, r in enumerate(rows)
    ]
    return _finish_rows(rows, gaps)


def build_classified_positions(laps: pd.DataFrame, teams: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    """Race / sprint: FastF1's race Position, gap as the difference between last laps (as before)."""
    rows = build_driver_rows(laps, teams)
    rows.sort(key=lambda r: (pd.isna(r["position_hint"]), r["position_hint"] if pd.notna(r["position_hint"]) else 0, r["driver_id"]))
    leader_last = rows[0]["last"] if rows else None
    gaps = []
    for i, r in enumerate(rows):
        if i == 0 or pd.isna(r["last"]) or leader_last is None or pd.isna(leader_last):
            gaps.append(None)
        else:
            gaps.append(f"+{abs((r['last'] - leader_last).total_seconds()):.3f}")
    return _finish_rows(rows, gaps)
