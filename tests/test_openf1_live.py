"""OpenF1 live source (#22): records -> timing board, the client, relays and the API around them.
Everything is served from a small made-up session through httpx.MockTransport — no network."""
import asyncio
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote

import httpx
import pytest
from fastapi.testclient import TestClient

import api.main as main
from api.main import app
from services import live_relay
from services.live_relay import LiveRelayManager
from services.mock_redis_service import MockRedisService
from services.openf1_live import OpenF1Client, build_state, find_session, laps_frame, track_status

T0 = datetime(2026, 9, 13, 13, 0, tzinfo=timezone.utc)


def iso(minutes: float) -> str:
    return (T0 + timedelta(minutes=minutes)).isoformat()


def lap(driver, number, start_min, duration, s=(30.0, 35.0, 35.0), pit_out=False):
    return {"driver_number": driver, "lap_number": number, "date_start": iso(start_min), "lap_duration": duration,
            "duration_sector_1": s[0], "duration_sector_2": s[1], "duration_sector_3": s[2], "is_pit_out_lap": pit_out}


SESSION = {"session_key": 99, "session_name": "Race", "date_start": iso(0), "date_end": iso(120),
           "meeting_key": 7, "year": 2026}
DATA = {
    "drivers": [{"driver_number": 12, "name_acronym": "ANT", "team_name": "Mercedes"},
                {"driver_number": 1, "name_acronym": "NOR", "team_name": "McLaren"},
                {"driver_number": 44, "name_acronym": "HAM", "team_name": "Ferrari"}],
    "laps": [lap(12, 1, 0, 100.0), lap(12, 2, 100 / 60, 98.0, (29.0, 34.0, 35.0)),
             lap(1, 1, 0, 101.0), lap(1, 2, 101 / 60, 99.5, (29.5, 34.5, 35.5)),
             lap(44, 1, 0, 103.0)],                           # HAM stops after one lap
    "stints": [{"driver_number": 12, "stint_number": 1, "lap_start": 1, "lap_end": 30, "compound": "MEDIUM", "tyre_age_at_start": 2},
               {"driver_number": 1, "stint_number": 1, "lap_start": 1, "lap_end": 1, "compound": "SOFT", "tyre_age_at_start": 0},
               {"driver_number": 1, "stint_number": 2, "lap_start": 2, "lap_end": 30, "compound": "HARD", "tyre_age_at_start": 0}],
    "pit": [{"driver_number": 1, "lap_number": 1, "date": iso(1.6), "lane_duration": 22.0}],
    "position": [{"driver_number": 12, "position": 1, "date": iso(0)}, {"driver_number": 1, "position": 2, "date": iso(0)},
                 {"driver_number": 44, "position": 3, "date": iso(0)}],
    "intervals": [{"driver_number": 1, "gap_to_leader": 2.5, "interval": 2.5, "date": iso(3)},
                  {"driver_number": 44, "gap_to_leader": "+1 LAP", "interval": None, "date": iso(3)}],
    "race_control": [{"category": "Flag", "flag": "GREEN", "scope": "Track", "message": "GREEN LIGHT", "date": iso(0)}],
}


# --- records -> board --------------------------------------------------------------------------

def test_the_race_board_uses_openf1_positions_gaps_and_tyres():
    state = build_state(DATA, SESSION, "R", "2026_Spanish_Grand_Prix", clock=T0 + timedelta(minutes=4))
    rows = {r["driver_id"]: r for r in state["positions"]}

    assert [r["driver_id"] for r in state["positions"]] == ["ANT", "NOR", "HAM"]
    assert state["session_type"] == "classified" and state["lap"] == 2 and state["source"] == "openf1"
    assert rows["ANT"]["gap"] is None and rows["NOR"]["gap"] == "+2.500" and rows["HAM"]["gap"] == "+1 LAP"
    assert (rows["ANT"]["tyre"], rows["ANT"]["tyre_age"]) == ("MEDIUM", 4)      # 2 laps old at the start + 2
    assert rows["NOR"]["stints"] == [{"compound": "SOFT", "laps": 1}, {"compound": "HARD", "laps": 1}]
    assert rows["ANT"]["best_lap_status"] == "purple" and rows["ANT"]["team"] == "Mercedes"
    assert [s["status"] for s in rows["ANT"]["sectors"]] == ["purple", "purple", "purple"]


def test_only_finished_laps_count_and_the_pit_lane_is_shown_while_a_car_is_in_it():
    early = build_state(DATA, SESSION, "R", "x", clock=T0 + timedelta(minutes=1.7))   # after lap 1, NOR in the lane
    rows = {r["driver_id"]: r for r in early["positions"]}

    assert rows["ANT"]["laps_completed"] == 1 and early["lap"] == 1
    assert rows["NOR"]["in_pit"] is True and rows["ANT"]["in_pit"] is False


def test_a_car_that_stops_completing_laps_is_marked_stopped():
    state = build_state(DATA, SESSION, "R", "x", clock=T0 + timedelta(minutes=9))

    ham = {r["driver_id"]: r for r in state["positions"]}["HAM"]
    assert ham["status"] == "Stopped" and ham["gap"] is None


def test_timed_sessions_rank_by_best_lap_and_list_drivers_with_no_time():
    data = {**DATA, "laps": [lap(1, 1, 0, 90.0), lap(12, 1, 0, 91.0)]}
    state = build_state(data, {**SESSION, "session_name": "Qualifying"}, "Q", "x", clock=T0 + timedelta(minutes=5))

    assert [(r["driver_id"], r["gap"], r["status"]) for r in state["positions"]] == [
        ("NOR", None, "Running"), ("ANT", "+1.000", "Running"), ("HAM", None, "No time")]


def test_track_status_from_race_control():
    msg = lambda cat, text, flag=None, scope="Track", m=0: {"category": cat, "message": text, "flag": flag, "scope": scope, "date": iso(m)}
    assert track_status([msg("SafetyCar", "SAFETY CAR DEPLOYED", m=1)]) == "sc"
    assert track_status([msg("SafetyCar", "VIRTUAL SAFETY CAR DEPLOYED", m=1), msg("SafetyCar", "VIRTUAL SAFETY CAR ENDING", m=2)]) == "green"
    assert track_status([msg("Flag", "RED FLAG", "RED", m=1)]) == "red"
    assert track_status([msg("Flag", "YELLOW IN TRACK SECTOR 4", "YELLOW", scope="Sector")]) == "green"
    assert track_status([msg("Flag", "CHEQUERED FLAG", "CHEQUERED", m=9), msg("Flag", "GREEN", "GREEN", m=1)]) == "chequered"


def test_the_race_is_finished_at_the_chequered_flag():
    data = {**DATA, "race_control": DATA["race_control"] + [
        {"category": "Flag", "flag": "CHEQUERED", "scope": "Track", "message": "CHEQUERED FLAG", "date": iso(4)}]}

    assert build_state(data, SESSION, "R", "x", clock=T0 + timedelta(minutes=3))["session_status"] == "live"
    assert build_state(data, SESSION, "R", "x", clock=T0 + timedelta(minutes=5))["session_status"] == "finished"


def test_every_driver_has_a_row_before_any_lap_is_finished():
    frame = laps_frame(DATA, clock=T0)
    assert sorted(frame["Driver"]) == ["ANT", "HAM", "NOR"] and frame["LapNumber"].isna().all()


# --- client ------------------------------------------------------------------------------------

def fake_openf1(requests):
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        path = request.url.path
        if path == "/token":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        name = path.rsplit("/", 1)[-1]
        if name == "meetings":
            return httpx.Response(200, json=[{"meeting_key": 7, "meeting_name": "Spanish Grand Prix"},
                                             {"meeting_key": 8, "meeting_name": "São Paulo Grand Prix"}])
        if name == "sessions":
            return httpx.Response(200, json=[{**SESSION, "session_name": "Qualifying", "session_key": 98}, SESSION])
        if name in DATA:
            return httpx.Response(200, json=DATA[name])
        return httpx.Response(404, json={"detail": "No results found."})
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_filters_with_operators_and_the_bearer_token():
    requests = []
    client = OpenF1Client(creds={"username": "u", "password": "p"}, per_minute=6000, transport=fake_openf1(requests))
    await client.get("position", session_key=99, **{"date>": iso(1)})
    await client.close()

    token_call, data_call = requests
    assert token_call.url.path == "/token" and b"username=u" in token_call.content
    assert unquote(str(data_call.url)).endswith(f"/v1/position?session_key=99&date>{iso(1)}")
    assert data_call.headers["Authorization"] == "Bearer tok"


@pytest.mark.asyncio
async def test_sessions_are_found_by_the_schedules_race_name():
    client = OpenF1Client(creds={}, per_minute=6000, transport=fake_openf1([]))
    assert (await find_session(client, 2026, "Spanish_Grand_Prix", "R"))["session_key"] == 99
    assert (await find_session(client, 2026, "Sao Paulo Grand Prix", "Q"))["session_key"] == 98   # accents ignored
    assert await find_session(client, 2026, "Spanish Grand Prix", "SQ") is None
    await client.close()


# --- relays ------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_replay_plays_the_session_into_redis_and_finishes(monkeypatch):
    async def no_wait(_):
        await asyncio.sleep(0)
    monkeypatch.setattr(live_relay, "_sleep", no_wait)   # real clock steps (3s x 120), no waiting
    redis = MockRedisService()
    data = {**DATA, "race_control": DATA["race_control"] + [
        {"category": "Flag", "flag": "CHEQUERED", "scope": "Track", "message": "CHEQUERED FLAG", "date": iso(4)}]}
    monkeypatch.setitem(globals(), "DATA", data)
    manager = LiveRelayManager(lambda: redis, client_factory=lambda: OpenF1Client(
        creds={}, per_minute=60000, transport=fake_openf1([])))

    relay = manager.start(2026, "Spanish Grand Prix", "R", replay_speed=120)
    await asyncio.wait_for(relay.task, timeout=20)

    assert relay.status == "finished" and relay.race_id == "2026_Spanish_Grand_Prix"
    state = (await redis.get_live_state("2026_Spanish_Grand_Prix"))["state"]
    assert state["replay"] is True and state["session_status"] == "finished" and state["leader"] == "ANT"


@pytest.mark.asyncio
async def test_live_relays_need_credentials(monkeypatch):
    monkeypatch.delenv("OPENF1_USERNAME", raising=False)
    assert LiveRelayManager.live_available() is False
    monkeypatch.setenv("OPENF1_USERNAME", "u")
    monkeypatch.setenv("OPENF1_PASSWORD", "p")
    assert LiveRelayManager.live_available() is True


# --- API ---------------------------------------------------------------------------------------

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main, "INTERNAL_API_KEY", "k")
    monkeypatch.delenv("OPENF1_USERNAME", raising=False)
    started = []

    def fake_start(year, gp, session, replay_speed=None):
        started.append((year, gp, session, replay_speed))
        return live_relay.Relay("2026_Spanish_Grand_Prix", year, gp, session, replay_speed, status="running")

    monkeypatch.setattr(main.live_relays, "start", fake_start)
    with TestClient(app) as c:
        c.started = started
        yield c


def test_live_status_without_credentials_or_relays_is_off(client):
    assert client.get("/live/status").json() == {"live_available": False, "enabled": False, "source": "openf1", "relays": []}


def test_starting_a_relay_needs_a_replay_speed_without_credentials(client):
    headers = {"X-Internal-Key": "k"}
    live = client.post("/admin/live/relay", json={"year": 2026, "gp": "Spanish Grand Prix", "session": "R"}, headers=headers)
    replay = client.post("/admin/live/relay", json={"year": 2026, "gp": "Spanish Grand Prix", "session": "R", "replay_speed": 20},
                         headers=headers)

    assert live.status_code == 400 and replay.status_code == 200
    assert client.started == [(2026, "Spanish Grand Prix", "R", 20.0)]
    assert client.post("/admin/live/relay", json={"year": 2026, "gp": "X", "session": "FP9", "replay_speed": 5},
                       headers=headers).status_code == 422
    assert client.post("/admin/live/relay", json={"year": 2026, "gp": "X", "replay_speed": 5}).status_code == 403
