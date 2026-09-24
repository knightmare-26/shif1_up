"""The post-session import: what the live poller and the Data Manager actually send.

The poller calls POST /admin/ingest/race with the internal key when a session ends; the Data Manager
calls POST /admin/ingest with years/laps. Both must keep working, and the single-race call must ingest
the session it was given (it used to be race-only). Nothing here touches FastF1 or a database.
"""
import pytest
from fastapi.testclient import TestClient

import api.main as main
from api.main import app

KEY = "test-internal-key"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main, "INTERNAL_API_KEY", KEY)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def ingested(monkeypatch):
    """Records what the background ingest was asked to do instead of fetching anything."""
    calls = {"single": [], "bulk": [], "trained": 0}

    async def fake_single(db, year, event, include_laps=False, session="R"):
        calls["single"].append({"year": year, "event": event, "laps": include_laps, "session": session})
        return {"race_id": f"{year}_x", "stored": True}

    async def fake_bulk(db, years, include_laps=False, include_practice=False):
        calls["bulk"].append({"years": years, "laps": include_laps, "practice": include_practice})

    async def fake_train(db):
        calls["trained"] += 1
        return {"success": True}

    monkeypatch.setattr(main.ingest_service, "ingest_single_race", fake_single)
    monkeypatch.setattr(main.ingest_service, "run_ingest", fake_bulk)
    monkeypatch.setattr(main.prediction_service, "train", fake_train)
    monkeypatch.setitem(main.ingest_service.status, "running", False)
    monkeypatch.setitem(main.ingest_service.status, "error", None)
    return calls


def poller_call(client, body):
    return client.post("/admin/ingest/race", json=body, headers={"X-Internal-Key": KEY})


@pytest.mark.parametrize("session", ["R", "S", "Q", "SQ", "FP1", "FP2", "FP3"])
def test_the_poller_can_ingest_every_session_it_can_follow(client, ingested, session):
    r = poller_call(client, {"year": 2026, "event": "Azerbaijan Grand Prix", "laps": False, "session": session})

    assert r.status_code == 200
    assert ingested["single"] == [{"year": 2026, "event": "Azerbaijan Grand Prix", "laps": False, "session": session}]
    assert ingested["trained"] == 1          # models retrain on the fresh data, as before


def test_a_call_with_no_session_still_ingests_the_race(client, ingested):
    """The poller before session support sent no session field."""
    r = poller_call(client, {"year": 2024, "event": "Bahrain", "laps": False})

    assert r.status_code == 200 and ingested["single"][0]["session"] == "R"


def test_a_round_number_event_is_still_accepted_as_a_number(client, ingested):
    poller_call(client, {"year": 2024, "event": "5", "session": "Q"})

    assert ingested["single"][0]["event"] == 5


def test_an_unknown_session_is_rejected_before_anything_is_ingested(client, ingested):
    r = poller_call(client, {"year": 2024, "event": "Bahrain", "session": "FP9"})

    assert r.status_code == 422 and ingested["single"] == []


def test_the_internal_key_is_still_required(client, ingested):
    r = client.post("/admin/ingest/race", json={"year": 2024, "event": "Bahrain"})

    assert r.status_code == 403 and ingested["single"] == []


def test_the_data_manager_bulk_ingest_is_unchanged(client, ingested, monkeypatch):
    """The Data Manager sends only years and laps — no `practice` — and that must keep working."""
    async def admin():
        return {"is_admin": True}

    app.dependency_overrides[main.get_current_user] = admin
    try:
        r = client.post("/admin/ingest", json={"years": [2023, 2024], "laps": True})
    finally:
        app.dependency_overrides.pop(main.get_current_user, None)

    assert r.status_code == 200
    assert ingested["bulk"] == [{"years": [2023, 2024], "laps": True, "practice": False}]
    assert ingested["trained"] == 1
