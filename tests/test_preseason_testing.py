"""Phase 3b (#35): preseason testing as the first evidence about a new era's cars."""
from datetime import datetime, timezone

import httpx
import numpy as np
import pandas as pd
import pytest

from services import preseason_testing as pt
from services.openf1_live import OpenF1Client

TESTING = {"year": 2026, "source": "openf1", "sessions": 3, "drivers": [
    {"driver_id": "ant", "team": "Mercedes", "best_lap": 90.0},
    {"driver_id": "rus", "team": "Mercedes", "best_lap": 90.9},
    {"driver_id": "lec", "team": "Ferrari", "best_lap": 90.45},
    {"driver_id": "ham", "team": "Ferrari", "best_lap": 91.8},
    {"driver_id": "bot", "team": "Cadillac", "best_lap": 99.0},
]}


def test_gaps_to_the_fastest_and_the_teams_quicker_car():
    g = pt.gaps({2026: TESTING}).set_index("driver_id")
    assert g.loc["ant", "driver_testing_gap_pct"] == 0
    assert g.loc["lec", "driver_testing_gap_pct"] == pytest.approx(0.5)
    assert g.loc["ham", "team_testing_gap_pct"] == pytest.approx(0.5)             # Leclerc's car
    assert g.loc["bot", "driver_testing_gap_pct"] == pt.GAP_CAP                   # capped


def race_rows(year, rounds, form=10.0):
    rows = []
    for rnd in rounds:
        for d, team in (("ant", "mercedes"), ("rus", "mercedes"), ("lec", "ferrari"), ("ham", "ferrari")):
            rows.append({"year": year, "round": rnd, "race_id": f"{year}_{rnd}", "driver_id": d, "constructor_id": team,
                         **{c: form for c in pt.FORM_FEATURES}})
    return pd.DataFrame(rows)


def test_the_rule_starts_an_era_from_the_testing_order_and_fades_out():
    df = pt.apply_testing(race_rows(2026, [1, 2, 3, 4]), {2026: TESTING}, "rule", races=3)
    first = df[df["round"] == 1].set_index("driver_id")

    # team pace first (more reliable in testing than one driver's lap), then the driver's own
    assert [first.loc[d, "driver_rolling_grid"] for d in ("ant", "rus", "lec", "ham")] == [1, 2, 3, 4]
    assert first.loc["ant", "constructor_rolling_finish"] == 1.5        # the Mercedes cars, 1 and 2
    second = df[df["round"] == 2].set_index("driver_id")
    assert second.loc["ant", "driver_rolling_grid"] == pytest.approx(2 / 3 * 1 + 1 / 3 * 10)
    assert (df[df["round"] == 4]["driver_rolling_grid"] == 10).all()     # faded out
    assert not set(pt.COLUMNS) & set(df.columns)                         # the rule adds no inputs


def test_the_rule_leaves_a_stable_season_alone():
    stable = {**TESTING, "year": 2025}
    df = pt.apply_testing(race_rows(2025, [1, 2]), {2025: stable}, "rule", races=3)
    assert (df["driver_rolling_grid"] == 10).all()


def test_as_features_testing_fades_to_the_seasons_median():
    df = pt.apply_testing(race_rows(2026, [1, 2, 3, 4]), {2026: TESTING}, "features", races=3)
    r1 = df[df["round"] == 1].set_index("driver_id")["driver_testing_gap_pct"]
    r4 = df[df["round"] == 4]["driver_testing_gap_pct"]
    assert r1["ant"] < r1["ham"] and r4.nunique() == 1


def test_an_upcoming_race_gets_the_rule_too():
    rows = race_rows(2026, [0]).drop(columns=["year", "round", "race_id"])
    first = pt.apply_to_upcoming(rows, {2026: TESTING}, 2026, race_no=1, races=3).set_index("driver_id")
    later = pt.apply_to_upcoming(rows, {2026: TESTING}, 2026, race_no=5, races=3)
    stable = pt.apply_to_upcoming(rows, {2025: {**TESTING, "year": 2025}}, 2025, race_no=1, races=3)

    assert first.loc["ant", "driver_rolling_grid"] == 1
    assert (later["driver_rolling_grid"] == 10).all() and (stable["driver_rolling_grid"] == 10).all()


# --- storing the season's testing -------------------------------------------------------------

def openf1(calls, finished_days):
    days = [{"session_key": 10 + i, "session_name": f"Day {i + 1}",
             "date_end": f"2027-02-{12 + i}T16:00:00+00:00" if i < finished_days else "2027-03-30T16:00:00+00:00"}
            for i in range(3)]

    def handler(request):
        name = request.url.path.rsplit("/", 1)[-1]
        calls.append(name)
        if name == "meetings":
            return httpx.Response(200, json=[{"meeting_key": 1, "meeting_name": "Pre-Season Testing", "is_cancelled": False}])
        if name == "sessions":
            return httpx.Response(200, json=days)
        if name == "drivers":
            return httpx.Response(200, json=[{"driver_number": n, "name_acronym": f"D{n:02d}", "team_name": f"T{n % 5}"}
                                             for n in range(1, 13)])
        if name == "stints":
            return httpx.Response(200, json=[])
        if name == "laps":
            return httpx.Response(200, json=[{"driver_number": n, "lap_number": 1, "lap_duration": 90 + n / 10}
                                             for n in range(1, 13)])
        return httpx.Response(404, json={})
    return httpx.MockTransport(handler)


class CacheDb:
    def __init__(self):
        self.cache = {}

    async def get_prediction_cache(self, circuit, session):
        return self.cache.get((circuit, session))

    async def set_prediction_cache(self, circuit, session, key, result):
        self.cache[(circuit, session)] = {"model_trained_at": key, "result": result}


@pytest.mark.asyncio
async def test_testing_is_stored_as_days_finish_and_not_refetched_without_a_new_day():
    db, calls = CacheDb(), []
    now = datetime(2027, 2, 14, 18, tzinfo=timezone.utc)
    client = OpenF1Client(creds={}, per_minute=60000, transport=openf1(calls, finished_days=2))

    assert await pt.refresh(db, client, 2027, "2027-03-07", now=now) is True
    assert db.cache[("_testing", "2027")]["result"]["sessions"] == 2
    calls.clear()
    assert await pt.refresh(db, client, 2027, "2027-03-07", now=now) is False
    assert "laps" not in calls                                            # nothing new: no lap downloads
    assert await pt.refresh(db, client, 2027, "2027-03-07", now=datetime(2027, 4, 1, tzinfo=timezone.utc)) is False


def test_a_new_eras_first_race_is_predicted_from_testing_but_the_title_simulation_is_not():
    from services.prediction_service import PredictionService
    from tests.test_prediction_training import FakeLgb, synthetic_raw

    raw = synthetic_raw(years=[2024, 2025], rounds_per_year=6, drivers=("ant", "rus", "lec", "ham")).assign(points=0.0)
    svc = PredictionService(model_dir="unused")
    svc._testing_data = {2026: TESTING}
    svc._fit(raw, FakeLgb())

    tested = svc._build_prediction_rows("circuit1", season=2026).set_index("driver_id")
    untested = svc._build_prediction_rows("circuit1", season=2026, use_testing=False).set_index("driver_id")
    assert tested.loc["ant", "driver_rolling_grid"] == 1 and tested.loc["ham", "driver_rolling_grid"] == 4
    assert untested.loc["ant", "driver_rolling_grid"] != 1 or untested.loc["ham", "driver_rolling_grid"] != 4
