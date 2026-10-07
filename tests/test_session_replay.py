"""Race Results weather and replays (services/session_replay.py and its endpoints). OpenF1 is faked
with httpx.MockTransport and the database with a dict."""
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

import api.main as main
from api.main import app
from services.openf1_live import OpenF1Client, OpenF1Locked, weather_at, weather_summary
from services.session_replay import ReplayUnavailable, SessionReplayService, session_key

T0 = datetime(2026, 9, 13, 13, 0, tzinfo=timezone.utc)


def iso(minutes: float) -> str:
    return (T0 + timedelta(minutes=minutes)).isoformat()


def reading(minutes, air, track, rain=0, wind=0.5, direction=90):
    return {"date": iso(minutes), "air_temperature": air, "track_temperature": track, "humidity": 60.0,
            "wind_speed": wind, "wind_direction": direction, "rainfall": rain, "pressure": 1010.0,
            "session_key": 99, "meeting_key": 7}


SESSION = {"session_key": 99, "session_name": "Race", "date_start": iso(0), "date_end": iso(120), "meeting_key": 7}
WEATHER = [reading(-5, 24.0, 40.0), reading(1, 25.3, 42.7), reading(60, 23.0, 38.0, rain=1), reading(125, 22.0, 35.0)]
DATA = {
    "drivers": [{"driver_number": 12, "name_acronym": "ANT", "team_name": "Mercedes"}],
    "laps": [{"driver_number": 12, "lap_number": 1, "date_start": iso(0), "lap_duration": 100.0,
              "duration_sector_1": 30.0, "duration_sector_2": 35.0, "duration_sector_3": 35.0}],
    "stints": [], "pit": [], "position": [{"driver_number": 12, "position": 1, "date": iso(0)}],
    "intervals": [], "race_control": [], "weather": WEATHER,
}


def fake_openf1(calls, locked=False):
    def handler(request: httpx.Request) -> httpx.Response:
        name = request.url.path.rsplit("/", 1)[-1]
        calls.append(name)
        if locked:
            return httpx.Response(401, json={"detail": "Live F1 session in progress. Global API access (including past sessions) is restricted to authenticated users until the session ends."})
        if name == "meetings":
            return httpx.Response(200, json=[{"meeting_key": 7, "meeting_name": "Spanish Grand Prix"}])
        if name == "sessions":
            return httpx.Response(200, json=[SESSION])
        return httpx.Response(200, json=DATA.get(name, []))
    return httpx.MockTransport(handler)


class FakeDb:
    def __init__(self):
        self.rows = {}

    async def get_prediction_cache(self, circuit, kind):
        return {"result": self.rows[(circuit, kind)]} if (circuit, kind) in self.rows else None

    async def set_prediction_cache(self, circuit, kind, trained_at, result):
        self.rows[(circuit, kind)] = result


def service(calls, db=None, locked=False):
    return SessionReplayService(lambda: db, client_factory=lambda: OpenF1Client(
        creds={}, per_minute=60000, transport=fake_openf1(calls, locked)))


# --- weather readings ------------------------------------------------------------------------

def test_weather_at_a_moment_converts_wind_to_kmh():
    w = weather_at(WEATHER, T0 + timedelta(minutes=2))

    assert (w["air_temperature"], w["track_temperature"], w["humidity"]) == (25.3, 42.7, 60.0)
    assert w["wind_speed_kmh"] == 1.8 and w["wind_direction"] == 90 and w["rain"] is False
    assert weather_at(WEATHER, T0 + timedelta(minutes=61))["rain"] is True


def test_the_summary_covers_the_session_only():
    summary = weather_summary(WEATHER, T0, T0 + timedelta(minutes=120))

    assert summary["at_start"]["air_temperature"] == 24.0          # last reading before the start
    assert summary["rain_during"] is True
    assert summary["air_range"] == [23.0, 25.3] and summary["track_range"] == [38.0, 42.7]   # 125' is after the end


# --- service -----------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_weather_is_stored_and_then_served_without_openf1():
    db, calls = FakeDb(), []
    first = await service(calls, db).weather(2026, "Spanish Grand Prix", "R")
    assert first["weather"]["rain_during"] is True and first["duration_seconds"] == 120 * 60 + 600
    assert calls == ["meetings", "sessions", "weather"]

    later_calls = []
    again = await service(later_calls, db, locked=True).weather(2026, "Spanish_Grand_Prix", "R")   # OpenF1 locked
    assert later_calls == [] and again["weather"] == first["weather"]


@pytest.mark.asyncio
async def test_a_live_session_lock_is_reported_not_swallowed():
    with pytest.raises(OpenF1Locked):
        await service([], FakeDb(), locked=True).weather(2026, "Spanish Grand Prix", "R")


@pytest.mark.asyncio
async def test_old_seasons_and_unfinished_sessions_are_unavailable():
    with pytest.raises(ReplayUnavailable):
        await service([]).weather(2022, "Spanish Grand Prix", "R")
    future = dict(SESSION, date_end=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat())
    svc = service([])
    svc._sessions[session_key(2026, "Spanish Grand Prix", "R")] = future
    with pytest.raises(ReplayUnavailable):
        await svc.frame(2026, "Spanish Grand Prix", "R", 60)


@pytest.mark.asyncio
async def test_a_replay_frame_is_the_board_and_weather_at_that_moment():
    calls = []
    svc = service(calls)
    frame = await svc.frame(2026, "Spanish Grand Prix", "R", 30 * 60)
    again = await svc.frame(2026, "Spanish Grand Prix", "R", 90 * 60)

    assert frame["state"]["replay"] is True and frame["state"]["leader"] == "ANT"
    assert frame["state"]["weather"]["air_temperature"] == 25.3 and again["state"]["weather"]["rain"] is True
    assert calls.count("laps") == 1                     # the session is loaded once, then kept


# --- endpoints ---------------------------------------------------------------------------------

@pytest.fixture
def client(monkeypatch):
    with TestClient(app) as c:
        yield c


def test_endpoints_answer_404_for_unavailable_and_503_while_openf1_is_locked(client, monkeypatch):
    async def unavailable(*a):
        raise ReplayUnavailable("Session data starts in 2023")

    async def locked(*a):
        raise OpenF1Locked("Live F1 session in progress")

    monkeypatch.setattr(main.session_replays, "weather", unavailable)
    r = client.get("/api/sessions/2021/R/weather", params={"gp": "Spanish Grand Prix"})
    assert r.status_code == 404 and r.json()["detail"] == "Session data starts in 2023"

    monkeypatch.setattr(main.session_replays, "frame", locked)
    r = client.get("/api/sessions/2026/R/replay", params={"gp": "Spanish Grand Prix", "t": 60})
    assert r.status_code == 503 and r.json()["detail"] == "live_session_lock"

    assert client.get("/api/sessions/2026/FP9/weather", params={"gp": "X"}).status_code == 422
