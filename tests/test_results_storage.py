"""How session results are numbered and stored (data-hygiene fixes from #23)."""
import pandas as pd
import pytest

from services.ingest_service import _extract_classified_results, _number_unclassified
from services.simple_duckdb_service import SimpleDuckDBService


class FakeSession:
    def __init__(self, rows):
        self.results = pd.DataFrame(rows)


def row(abbr, position, status="Finished"):
    return {"Abbreviation": abbr, "Position": position, "GridPosition": 1, "Time": None, "Status": status,
            "TeamId": "team", "Points": 0, "Laps": 50}


def test_unclassified_drivers_get_the_positions_after_the_classified_ones():
    session = FakeSession([row("AAA", 1), row("BBB", 2), row("CCC", None, "Did not start"), row("DDD", None, "Disqualified")])

    results = _extract_classified_results(session, "R")

    assert [(r["driver_id"], r["position"]) for r in results] == [("aaa", 1), ("bbb", 2), ("ccc", 3), ("ddd", 4)]
    assert len({r["position"] for r in results}) == 4   # nobody shares P99 and overwrites anyone


def test_numbering_skips_positions_already_taken():
    results = _number_unclassified([{"position": 2}, {"position": None}, {"position": 1}, {"position": None}])

    assert [r["position"] for r in results] == [2, 3, 1, 4]


@pytest.mark.asyncio
async def test_storing_a_session_again_replaces_it_instead_of_leaving_stale_rows(tmp_path):
    db = SimpleDuckDBService(str(tmp_path / "t.duckdb"))
    await db.initialize()
    old = [{"position": 1, "driver_id": "aaa"}, {"position": 2, "driver_id": "bbb"}, {"position": 99, "driver_id": "bbb"}]
    new = [{"position": 1, "driver_id": "aaa"}, {"position": 2, "driver_id": "bbb"}]
    await db.store_race_results("2026_X", old, "sprint")
    await db.store_race_results("2026_X", [{"position": 1, "driver_id": "zzz"}], "race")

    assert await db.store_race_results("2026_X", new, "sprint")

    rows = await db._run_query("SELECT session_type, position, driver_id FROM race_results ORDER BY session_type, position")
    assert [(r["session_type"], r["position"], r["driver_id"]) for r in rows] == [
        ("race", 1, "zzz"),                       # the other session is untouched
        ("sprint", 1, "aaa"), ("sprint", 2, "bbb"),
    ]
    await db.cleanup()


class FakeDb:
    """Two rounds: one held a week ago (with a sprint), one five weeks ago."""
    def __init__(self):
        self.stored = {("2026_A", "race"): [{"position": 1, "driver_id": "aaa", "points": 25}],
                       ("2026_A", "sprint"): [{"position": 1, "driver_id": "aaa", "points": 8}],
                       ("2026_A", "qualifying"): [{"position": 1, "driver_id": "aaa", "points": 0}],
                       ("2026_B", "race"): [{"position": 1, "driver_id": "bbb", "points": 25}]}

    async def get_races_by_year(self, year):
        return [{"race_id": "2026_A", "round": 5, "date": "2026-09-17"},
                {"race_id": "2026_B", "round": 1, "date": "2026-08-20"}] if year == 2026 else []

    async def get_race_results(self, race_id, session_type):
        return list(self.stored.get((race_id, session_type), []))


@pytest.mark.asyncio
async def test_recent_rounds_are_re_fetched_and_changes_reported(monkeypatch):
    from datetime import date
    from services import ingest_service

    db, fetched = FakeDb(), []

    async def fake_ingest(db_, year, round_n, include_laps=False, session="R"):
        fetched.append((round_n, session))
        if session == "R":  # a penalty: the race winner changed
            db.stored[("2026_A", "race")] = [{"position": 1, "driver_id": "ccc", "points": 25}]

    monkeypatch.setattr(ingest_service, "ingest_single_race", fake_ingest)

    changed = await ingest_service.refresh_recent_results(db, days=14, today=date(2026, 9, 24))

    assert fetched == [(5, "R"), (5, "S"), (5, "Q")]          # only the round within 14 days
    assert changed == [{"race_id": "2026_A", "session_type": "race"}]
