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
        assert set(checks.keys()) == {"redis", "duckdb"}

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
