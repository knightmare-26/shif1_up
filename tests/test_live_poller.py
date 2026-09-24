"""Live poller: which session it follows, and how each kind of session is ranked.

Race/sprint are classified (race Position, lap counter). Practice and qualifying
have neither — drivers are ordered by best lap — and used to be shown with a race
table that made no sense for them (and would ingest the wrong session at the end).
"""
import asyncio

import pandas as pd
import pytest

from live import poller
from live.poller import LivePoller, build_race_id, build_timed_positions, is_timed_session


def td(seconds):
    return pd.Timedelta(seconds=seconds)


def lap(driver, number, seconds, compound="SOFT"):
    return {"Driver": driver, "LapNumber": number, "LapTime": td(seconds) if seconds else pd.NaT, "Compound": compound}


def make_poller(session="R", poll_interval=5):
    p = LivePoller.__new__(LivePoller)          # skip __init__: it needs Redis and a FastF1 cache dir
    p.session_code = session
    p.poll_interval = poll_interval
    p.stall_polls = 0
    p.session = None
    return p


def test_the_race_keeps_its_bare_id_and_other_sessions_get_a_suffix():
    assert build_race_id(2026, "Belgian Grand Prix") == "2026_Belgian_Grand_Prix"
    assert build_race_id(2026, "Belgian Grand Prix", "R") == "2026_Belgian_Grand_Prix"
    for code in ("FP1", "FP2", "FP3", "SQ", "S", "Q"):
        assert build_race_id(2026, "Belgian Grand Prix", code) == f"2026_Belgian_Grand_Prix_{code}"
    assert build_race_id(2026, "Emilia/Romagna", "Q") == "2026_Emilia-Romagna_Q"


def test_only_practice_and_qualifying_are_timed_sessions():
    assert {c for c in poller.SESSIONS if is_timed_session(c)} == {"FP1", "FP2", "FP3", "SQ", "Q"}
    assert not is_timed_session("R") and not is_timed_session("S")


def test_an_unknown_session_is_rejected():
    with pytest.raises(ValueError):
        LivePoller("redis://x", "cache", 2026, "Belgian Grand Prix", session="FP9")


def test_timed_positions_are_ordered_by_best_lap_with_gap_to_the_fastest():
    laps = pd.DataFrame([
        lap("VER", 1, 92.5), lap("VER", 2, 91.377), lap("VER", 3, 95.0),   # best 91.377, last 95.0
        lap("NOR", 1, 91.204),
        lap("LEC", 1, 91.902), lap("LEC", 2, 93.0),
    ])

    rows = build_timed_positions(laps)

    assert [r["driver_id"] for r in rows] == ["NOR", "VER", "LEC"]
    assert [r["position"] for r in rows] == [1, 2, 3]
    assert rows[0]["gap"] is None and rows[0]["best_lap_time"] == "1:31.204"
    assert rows[1]["gap"] == "+0.173" and rows[1]["best_lap_time"] == "1:31.377"
    assert rows[1]["last_lap_time"] == "1:35.000"      # last lap, not the best
    assert rows[1]["laps_completed"] == 3 and rows[2]["laps_completed"] == 2


def test_a_driver_with_no_timed_lap_is_listed_last_not_dropped():
    laps = pd.DataFrame([lap("NOR", 1, 91.2), lap("ALB", 1, None, "HARD"), lap("VER", 1, 92.0)])

    rows = build_timed_positions(laps)

    assert [r["driver_id"] for r in rows] == ["NOR", "VER", "ALB"]
    assert rows[-1]["status"] == "No time" and rows[-1]["best_lap_time"] is None and rows[-1]["gap"] is None
    assert rows[0]["status"] == "Running"


def test_a_timed_session_ends_after_a_long_stall_with_no_leader_status_needed():
    p = make_poller("FP1", poll_interval=5)                 # 300s / 5s = 60 polls
    p.stall_polls = 59
    assert asyncio.run(p._check_session_ended()) is False
    p.stall_polls = 60
    assert asyncio.run(p._check_session_ended()) is True


def test_a_classified_session_still_needs_a_terminal_leader_status():
    p = make_poller("R")
    p.stall_polls = 10
    p.session = type("S", (), {"results": pd.DataFrame([{"Status": ""}])})()
    assert asyncio.run(p._check_session_ended()) is False    # stalled, but the leader is still "running"
    p.session = type("S", (), {"results": pd.DataFrame([{"Status": "Finished"}])})()
    assert asyncio.run(p._check_session_ended()) is True


def test_persisting_a_session_ingests_that_session_not_the_race(monkeypatch):
    posted = {}

    class Resp:
        status = 200
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def text(self): return ""

    class Http:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        def post(self, url, json=None, headers=None, timeout=None):
            posted.update(url=url, json=json)
            return Resp()

    monkeypatch.setattr(poller.aiohttp, "ClientSession", lambda: Http())
    p = make_poller("Q")
    p.race_year, p.race_gp, p.race_id, p.is_polling = 2026, "Belgian Grand Prix", "2026_Belgian_Grand_Prix_Q", True

    asyncio.run(p._persist_and_stop())

    assert posted["json"]["session"] == "Q" and posted["json"]["year"] == 2026
    assert p.is_polling is False


# ---- timing-board fields ---------------------------------------------------

def full_lap(driver, number, lap_s, s1, s2, s3, compound="SOFT", stint=1, life=1, position=None, pit_in=False):
    row = {"Driver": driver, "LapNumber": number, "LapTime": td(lap_s) if lap_s else pd.NaT,
           "Sector1Time": td(s1) if s1 else pd.NaT, "Sector2Time": td(s2) if s2 else pd.NaT,
           "Sector3Time": td(s3) if s3 else pd.NaT, "Compound": compound, "Stint": stint, "TyreLife": life,
           "PitInTime": td(1) if pit_in else pd.NaT, "Position": position}
    return row


def board_laps():
    return pd.DataFrame([
        # NOR: latest lap (2) is slower than lap 1 in S1 only
        full_lap("NOR", 1, 91.0, 30.0, 30.0, 31.0, life=1),
        full_lap("NOR", 2, 92.0, 31.0, 30.0, 31.0, life=2),
        # VER: fastest S2 of the session; latest lap is his own best in S1 and S3
        full_lap("VER", 1, 93.0, 32.0, 31.0, 32.0, "MEDIUM", stint=1, life=3),
        full_lap("VER", 2, 92.5, 31.5, 29.5, 31.5, "HARD", stint=2, life=1, pit_in=True),
        # ALB: one lap with no time, no sector 3
        full_lap("ALB", 1, None, 33.0, 32.0, None, "HARD", life=1),
    ])


def by_driver(rows):
    return {r["driver_id"]: r for r in rows}


def test_best_lap_is_purple_only_for_the_session_fastest():
    rows = by_driver(build_timed_positions(board_laps()))
    assert rows["NOR"]["best_lap_status"] == "purple" and rows["NOR"]["best_lap_time"] == "1:31.000"
    assert rows["VER"]["best_lap_status"] == "green"
    assert rows["ALB"]["best_lap_status"] is None


def test_sector_colours_follow_session_best_personal_best_and_missing_times():
    rows = by_driver(build_timed_positions(board_laps()))
    nor = [s["status"] for s in rows["NOR"]["sectors"]]
    ver = [s["status"] for s in rows["VER"]["sectors"]]
    alb = [s["status"] for s in rows["ALB"]["sectors"]]

    assert nor == ["yellow", "green", "purple"]       # S1 slower than his own best; S2 = his best; S3 = fastest of the session
    assert ver == ["green", "purple", "green"]        # S2 (29.5) is the fastest of the whole session; S1/S3 are his own bests
    assert alb == ["green", "green", "none"]          # his only lap is his best; sector 3 not completed
    assert rows["VER"]["sectors"][1]["time"] == "29.500"


def test_tyre_age_stint_history_and_in_pit_flag():
    rows = by_driver(build_timed_positions(board_laps()))
    ver = rows["VER"]
    assert ver["tyre"] == "HARD" and ver["tyre_age"] == 1
    assert ver["stints"] == [{"compound": "MEDIUM", "laps": 1}, {"compound": "HARD", "laps": 1}]
    assert ver["in_pit"] is True and rows["NOR"]["in_pit"] is False


def test_team_comes_from_the_session_results():
    rows = by_driver(build_timed_positions(board_laps(), {"NOR": "McLaren"}))
    assert rows["NOR"]["team"] == "McLaren" and rows["VER"]["team"] is None


def test_classified_sessions_are_ordered_by_race_position_with_the_same_fields():
    laps = pd.DataFrame([
        full_lap("VER", 1, 93.0, 31, 31, 31, position=2),
        full_lap("NOR", 1, 92.0, 30, 31, 31, position=1),
        full_lap("LEC", 1, 94.5, 32, 31, 31, position=3),
    ])

    rows = poller.build_classified_positions(laps)

    assert [r["driver_id"] for r in rows] == ["NOR", "VER", "LEC"]
    assert rows[0]["gap"] is None and rows[1]["gap"] == "+1.000" and rows[2]["gap"] == "+2.500"
    assert rows[0]["best_lap_status"] == "purple" and len(rows[0]["sectors"]) == 3 and rows[0]["stints"]


def test_the_poller_starts_as_a_standalone_script():
    """conftest.py puts api/ on sys.path, which hid a real bug: run as `python live/poller.py` the
    poller couldn't import redis_service (it imports `services.redact`) and died before doing anything."""
    import subprocess, sys, pathlib
    root = pathlib.Path(__file__).resolve().parent.parent
    result = subprocess.run([sys.executable, str(root / "live" / "poller.py"), "--help"],
                            capture_output=True, text=True, cwd=str(root.parent), timeout=60)
    assert result.returncode == 0, result.stderr[-500:]
    assert "--session" in result.stdout
