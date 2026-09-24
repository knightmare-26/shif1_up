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
