"""Phase 4 — Live Data tests.

Covers:
- `_unwrap_live_state` envelope flattening (unit)
- `POST /simulate/live/{race_id}` and `GET /live/{race_id}/state` (integration)
- `WS /ws/live/{race_id}` initial-state delivery with flat payload (integration)

These tests rely on the mock Redis fallback — no real Redis needed.
"""

import pytest
from fastapi.testclient import TestClient

from api.main import app, _unwrap_live_state


# --------------------------------------------------------------------------- #
# Unit: envelope flattening
# --------------------------------------------------------------------------- #

class TestUnwrapLiveState:
    def test_none_envelope_returns_none(self):
        assert _unwrap_live_state(None) is None
        assert _unwrap_live_state({}) is None

    def test_state_envelope_is_flattened(self):
        inner = {"session_status": "live", "lap": 3, "positions": []}
        envelope = {"race_id": "2024_Bahrain", "timestamp": "t", "state": inner}
        assert _unwrap_live_state(envelope) == inner

    def test_update_envelope_is_flattened(self):
        inner = {"session_status": "live", "lap": 7, "positions": []}
        envelope = {
            "race_id": "2024_Bahrain",
            "timestamp": "t",
            "update": {"type": "state_update", "state": inner},
        }
        assert _unwrap_live_state(envelope) == inner

    def test_flat_envelope_passes_through(self):
        flat = {"session_status": "live", "lap": 1, "positions": []}
        assert _unwrap_live_state(flat) == flat

    def test_non_dict_state_is_not_unwrapped(self):
        # Defensive: if `state` is not a dict, we should not crash or unwrap it.
        envelope = {"state": "oops"}
        assert _unwrap_live_state(envelope) == envelope


# --------------------------------------------------------------------------- #
# Integration: simulate + live state REST
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def client():
    """TestClient with lifespan — spins up mock Redis, DuckDB, etc."""
    with TestClient(app) as c:
        yield c


class TestSimulateEndpoint:
    def test_simulate_populates_live_state_with_canonical_fields(self, client):
        client.post("/simulate/live/2024_CanonicalGP")
        r = client.get("/live/2024_CanonicalGP/state")
        assert r.status_code == 200
        state = r.json()

        # Flattened envelope — no nested {state: ...} wrapper.
        assert "state" not in state or not isinstance(state.get("state"), dict)
        assert state["session_status"] == "live"
        assert state["lap"] == 15
        assert state["total_laps"] == 57
        assert state["track_status"] == "green"
        assert state["leader"] == "VER"

        positions = state["positions"]
        assert len(positions) >= 2
        first = positions[0]
        # Canonical field names expected by the frontend LiveState interface.
        for key in ("driver_id", "driver_name", "position", "status", "last_lap_time"):
            assert key in first, f"missing {key} in position payload"
        assert first["driver_id"] == "VER"
        assert first["position"] == 1


class TestSimulateSessions:
    @staticmethod
    def _assert_timing_board_fields(positions):
        first = positions[0]
        assert first["best_lap_status"] == "purple" and all(p["best_lap_status"] in ("green", None) for p in positions[1:])
        assert len(first["sectors"]) == 3 and {s["status"] for s in first["sectors"]} <= {"purple", "green", "yellow", "none"}
        assert first["tyre"] and first["tyre_age"] is not None and first["stints"] and first["team"]
        assert any(p["in_pit"] for p in positions)

    def test_race_simulation_is_classified_and_keeps_its_lap_counter(self, client):
        client.post("/simulate/live/2024_SimRace")
        state = client.get("/live/2024_SimRace/state").json()
        assert state["session_type"] == "classified" and state["session"] == "R"
        assert state["lap"] == 15
        assert state["leader"] == "VER" and len(state["positions"]) == 22
        self._assert_timing_board_fields(state["positions"])

    @pytest.mark.parametrize("session", ["FP1", "FP2", "FP3", "SQ", "Q"])
    def test_timed_sessions_are_best_lap_ordered_with_no_lap_counter(self, client, session):
        race_id = f"2024_SimTimed_{session}"          # a session-qualified id works unchanged
        assert client.post(f"/simulate/live/{race_id}?session={session}").status_code == 200

        state = client.get(f"/live/{race_id}/state").json()

        assert state["session_type"] == "timed" and state["session"] == session
        assert "lap" not in state and "total_laps" not in state
        positions = state["positions"]
        assert positions[0]["position"] == 1 and positions[0]["gap"] is None
        assert all("best_lap_time" in p and "laps_completed" in p for p in positions)
        assert positions[-1]["status"] == "No time"     # a driver with no timed lap is listed last
        self._assert_timing_board_fields(positions)

    def test_an_unknown_session_is_rejected(self, client):
        assert client.post("/simulate/live/2024_SimBad?session=FP9").status_code == 422

    def test_the_sprint_is_classified(self, client):
        client.post("/simulate/live/2024_SimSprint_S?session=S")
        assert client.get("/live/2024_SimSprint_S/state").json()["session_type"] == "classified"

    def test_ingest_only_accepts_known_sessions(self, client):
        r = client.post("/admin/ingest/race", json={"year": 2024, "event": "1", "session": "FP9"})
        assert r.status_code in (401, 403, 422)          # rejected either at auth or validation, never ingested


class TestLiveSessionsEndpoint:
    def test_lists_only_the_sessions_that_have_state_and_marks_fresh_ones_live(self, client):
        client.post("/simulate/live/2024_SessionsGP")                       # race
        client.post("/simulate/live/2024_SessionsGP_FP1?session=FP1")       # practice 1

        body = client.get("/live/2024_SessionsGP/sessions").json()

        sessions = {s["session"]: s for s in body["sessions"]}
        assert set(sessions) == {"R", "FP1"}
        assert sessions["FP1"]["race_id"] == "2024_SessionsGP_FP1" and sessions["FP1"]["session_type"] == "timed"
        assert sessions["R"]["session_type"] == "classified"
        assert all(s["live"] for s in sessions.values())              # just written, so within the freshness window

    def test_a_session_the_poller_stopped_refreshing_is_listed_but_not_live(self, client):
        from datetime import datetime, timedelta
        import api.main as main
        stale = {"race_id": "2024_StaleGP_Q", "session": "Q", "session_type": "timed", "session_status": "live",
                 "positions": [{"driver_id": "NOR", "position": 1}],
                 "timestamp": (datetime.utcnow() - timedelta(minutes=10)).isoformat()}
        client.portal.call(main.redis_service.set_live_state, "2024_StaleGP_Q", stale)

        sessions = client.get("/live/2024_StaleGP/sessions").json()["sessions"]

        assert [(s["session"], s["live"]) for s in sessions] == [("Q", False)]

    def test_a_weekend_with_nothing_published_is_empty(self, client):
        assert client.get("/live/2024_NothingHere/sessions").json()["sessions"] == []


class TestLiveStateEndpoint:
    def test_live_state_when_no_data(self, client):
        r = client.get("/live/9999_NothingPublished/state")
        assert r.status_code == 200
        data = r.json()
        assert data["session_status"] == "no_data"
        assert "No live data available" in data["message"]


# --------------------------------------------------------------------------- #
# Integration: WebSocket flat delivery
# --------------------------------------------------------------------------- #

class TestWebSocketLive:
    def test_ws_sends_flat_initial_state_after_simulate(self, client):
        race_id = "2024_WsInitial"
        client.post(f"/simulate/live/{race_id}")

        with client.websocket_connect(f"/ws/live/{race_id}") as ws:
            msg = ws.receive_json()

        assert msg["type"] == "initial_state"
        data = msg["data"]

        # Frontend reads msg.data as a flat LiveState — assert that shape.
        assert data["session_status"] == "live"
        assert data["lap"] == 15
        assert isinstance(data["positions"], list) and data["positions"]
        assert data["positions"][0]["driver_id"] == "VER"

        # Should not be double-wrapped.
        assert "state" not in data or not isinstance(data.get("state"), dict)
        assert "update" not in data

    def test_ws_connects_with_no_data(self, client):
        # Without a preceding simulate, no initial_state should be pushed;
        # the connection should still open cleanly.
        race_id = "2024_WsEmpty"
        with client.websocket_connect(f"/ws/live/{race_id}") as ws:
            # Nothing to receive deterministically — just confirm the handshake.
            assert ws is not None


# --------------------------------------------------------------------------- #
# Integration: /health hardened probe (Phase 6)
# --------------------------------------------------------------------------- #

class TestHealthEndpoint:
    def test_health_shape(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()

        # Top-level envelope
        assert body["service"] == "Shif1 UP API"
        assert body["status"] in ("ok", "degraded", "error")
        assert "timestamp" in body
        assert "version" in body

        # Per-dependency checks
        checks = body["checks"]
        # "database" is only present when running against Supabase (DATABASE_URL set).
        assert set(checks.keys()) - {"database"} == {"redis", "duckdb"}
        if "database" in checks:
            assert checks["database"]["state"] in ("ready", "connecting", "waking", "unavailable")
            assert checks["database"]["self_healing"] is True

    def test_health_reports_redis_kind_and_probes_duckdb(self, client):
        r = client.get("/health")
        body = r.json()

        redis_check = body["checks"]["redis"]
        # In the test environment we fall back to MockRedisService.
        assert redis_check["status"] == "ok"
        assert redis_check["kind"] == "mock"

        duckdb_check = body["checks"]["duckdb"]
        assert duckdb_check["status"] == "ok"
        assert "path" in duckdb_check

    def test_health_overall_ok_with_mock_redis(self, client):
        # Mock Redis is a valid fallback — overall should be "ok", not "degraded".
        r = client.get("/health")
        assert r.json()["status"] == "ok"
