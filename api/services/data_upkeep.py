"""
Keeps the stored data complete and correct by itself, so nothing depends on someone running a
script against production after a change ships (the prediction work needed several: qualifying
for 2022-25, re-fetching sprint qualifying, preseason testing, a P99 row).

Runs from the API's background loop with Supabase (main._data_upkeep_loop), a small batch per run
so it never strains OpenF1's free tier (30 requests a minute) or the free instance:

1. positions — a session whose positions run far past its number of drivers (an old unclassified
   driver stored at P99) gets them renumbered after the classified ones;
2. missed races — a round of this or last season that's been raced but has no results (the server
   slept through the 14-day results refresh) is ingested from FastF1: race, then sprint if any;
3. weekend sessions (2023 on) — practice, sprint qualifying and qualifying a raced weekend should
   have but doesn't, and sprint qualifying stored without times (FastF1's feed order), from OpenF1;
4. preseason testing (2023 on) for seasons that don't have it, once their testing is over;
5. weather (2023 on) for stored sessions that don't have it;
6. the title race's track record, once a season has finished and isn't in it, or when the title
   simulation's method changed (championship_service.TITLE_BACKTEST_VERSION).

What it can't get (a session OpenF1 doesn't have, a race FastF1 won't load) is remembered for the
life of the process and retried after a cold start, so a gap can't cost requests on every run.
"""
import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from services import preseason_testing
from services.openf1_live import OpenF1Client, OpenF1Locked, find_session
from services.openf1_results import classified_rows, weekend_teams
from services.weekend_practice import session_rows

logger = logging.getLogger(__name__)

FIRST_OPENF1 = 2023
SESSION_BATCH = 8           # OpenF1 sessions fetched per run
WEATHER_BATCH = 8
RACE_BATCH = 2              # FastF1 loads per run
RETRY_AFTER = 6 * 3600      # a failed FastF1 load is tried again after this (in-process)
P99_SLACK = 5               # positions this far past the number of drivers are an old placeholder

CODES = {"fp1": "FP1", "fp2": "FP2", "fp3": "FP3", "sprint_qualifying": "SQ", "qualifying": "Q",
         "sprint": "S", "race": "R"}
OPENF1_SESSIONS = ("fp1", "fp2", "fp3", "sprint_qualifying", "qualifying")


def expected_sessions(year: int, sprint_weekend: bool) -> List[str]:
    """What a raced weekend should have stored (a sprint weekend has one practice session)."""
    practice = ["fp1"] if sprint_weekend else ["fp1", "fp2", "fp3"]
    return practice + (["sprint_qualifying"] if sprint_weekend and year >= FIRST_OPENF1 else []) + ["qualifying"]


@dataclass
class Report:
    renumbered: List[str] = field(default_factory=list)
    races: List[str] = field(default_factory=list)
    sessions: List[str] = field(default_factory=list)
    testing: List[int] = field(default_factory=list)
    weather: List[str] = field(default_factory=list)
    title_backtest: bool = False

    @property
    def needs_retrain(self) -> bool:
        return bool(self.renumbered or self.races or self.sessions or self.testing)

    def summary(self) -> str:
        parts = [f"{len(v)} {k}" for k, v in (("renumbered", self.renumbered), ("races", self.races),
                                               ("sessions", self.sessions), ("testing", self.testing),
                                               ("weather", self.weather)) if v]
        return ", ".join(parts + (["title backtest"] if self.title_backtest else [])) or "nothing to do"


class DataUpkeep:
    def __init__(self, ingest_race: Callable, load_weather: Callable, rebuild_title_backtest: Callable,
                 title_backtest_version: Optional[str] = None):
        """`ingest_race(db, year, round, session)` stores a session from FastF1 (ingest_service);
        `load_weather(year, gp, code)` fetches and stores a session's weather (SessionReplayService);
        `rebuild_title_backtest()` recomputes and stores the title race's track record."""
        self.ingest_race = ingest_race
        self.load_weather = load_weather
        self.rebuild_title_backtest = rebuild_title_backtest
        self.title_backtest_version = title_backtest_version
        self._unavailable: Set[Tuple] = set()       # (race_id, session_type) OpenF1 doesn't have
        self._failed_at: Dict[Tuple, float] = {}    # FastF1 loads that failed, and when

    async def run(self, db, client: OpenF1Client, constructor_names: Dict[str, str],
                  last_teams: Dict[str, str], now: Optional[datetime] = None) -> Report:
        now = now or datetime.now(timezone.utc)
        today = now.date()
        report = Report()
        stored = await self._stored_sessions(db)
        races = {}
        for year in range(FIRST_OPENF1 - 1, today.year + 1):
            for race in await db.get_races_by_year(year):
                races[race["race_id"]] = {**race, "year": int(race.get("year") or year)}

        await self._renumber(db, stored, report)
        await self._missed_races(db, races, stored, today, report)
        memo: Dict[Any, Any] = {}
        try:
            await self._weekend_sessions(db, client, races, stored, constructor_names, last_teams, memo, report)
            await self._testing(db, client, races, now, report)
            await self._weather(db, races, stored, report)
        except OpenF1Locked:
            logger.info("data upkeep: OpenF1 is locked while a session is live — the rest waits for the next run")
        await self._title_backtest(db, races, today, report)
        return report

    # ---- what's stored ------------------------------------------------------------------------

    @staticmethod
    async def _stored_sessions(db) -> Dict[Tuple[str, str], Dict[str, Any]]:
        rows = await db._run_query(
            "SELECT race_id, session_type, COUNT(*) AS n, MAX(position) AS top, "
            "COUNT(NULLIF(time, '')) AS timed FROM race_results GROUP BY race_id, session_type")
        return {(r["race_id"], r["session_type"]): {"n": int(r["n"]), "top": int(r["top"] or 0), "timed": int(r["timed"] or 0)}
                for r in rows}

    # ---- 1. positions -------------------------------------------------------------------------

    async def _renumber(self, db, stored, report: Report) -> None:
        for (race_id, session_type), info in stored.items():
            if info["top"] <= info["n"] + P99_SLACK:
                continue
            rows = sorted(await db.get_race_results(race_id, session_type), key=lambda r: r["position"])
            valid = [r for r in rows if r["position"] <= len(rows)]
            nxt = max((r["position"] for r in valid), default=0)
            fixed = []
            for r in rows:
                position = r["position"]
                if position > len(rows):
                    nxt += 1
                    position = nxt
                fixed.append({k: r.get(k) for k in ("driver_id", "constructor_id", "grid", "points", "time",
                                                     "fastest_lap", "fastest_lap_time", "status", "laps_completed")}
                             | {"position": position})
            await db.store_race_results(race_id, fixed, session_type)
            report.renumbered.append(f"{race_id} {session_type}")
            logger.info("data upkeep: renumbered %s %s (positions up to %d for %d drivers)",
                        race_id, session_type, info["top"], info["n"])

    # ---- 2. missed races ----------------------------------------------------------------------

    async def _missed_races(self, db, races, stored, today: date, report: Report) -> None:
        todo = []
        for race in races.values():
            day = _race_day(race)
            if day is None or race["year"] < today.year - 1 or day >= today - timedelta(days=1):
                continue
            if (race["race_id"], "race") not in stored:
                todo.append(race)
        for race in sorted(todo, key=lambda r: (r["year"], int(r["round"])))[:RACE_BATCH]:
            key = (race["race_id"], "race")
            if time.monotonic() - self._failed_at.get(key, -RETRY_AFTER) < RETRY_AFTER:
                continue
            try:
                result = await self.ingest_race(db, race["year"], int(race["round"]), "R")
            except Exception as exc:
                result = {"stored": False, "reason": str(exc)}
            if not result.get("stored"):
                self._failed_at[key] = time.monotonic()
                logger.warning("data upkeep: %s has no results yet (%s)", race["race_id"], str(result.get("reason"))[:100])
                continue
            report.races.append(race["race_id"])
            try:                                     # a sprint, if the weekend had one
                sprint = await self.ingest_race(db, race["year"], int(race["round"]), "S")
                if sprint.get("stored"):
                    report.races.append(f"{race['race_id']} sprint")
            except Exception:
                pass

    # ---- 3. weekend sessions ------------------------------------------------------------------

    async def _weekend_sessions(self, db, client, races, stored, constructor_names, last_teams, memo,
                                report: Report) -> None:
        todo = []
        for race in races.values():
            race_id, year = race["race_id"], race["year"]
            if year < FIRST_OPENF1 or (race_id, "race") not in stored:
                continue
            sprint = (race_id, "sprint") in stored
            for session_type in expected_sessions(year, sprint):
                info = stored.get((race_id, session_type))
                broken = session_type == "sprint_qualifying" and info is not None and info["timed"] == 0
                if (info is None or broken) and (race_id, session_type) not in self._unavailable:
                    todo.append((race, session_type))
        for race, session_type in sorted(todo, key=lambda t: (-t[0]["year"], -int(t[0]["round"])))[:SESSION_BATCH]:
            race_id, code = race["race_id"], CODES[session_type]
            session = await find_session(client, race["year"], race.get("gp") or race_id, code, memo)
            if session is None:
                self._unavailable.add((race_id, session_type))
                continue
            teams = {**last_teams, **await weekend_teams(db, race_id)}
            if session_type in ("qualifying", "sprint_qualifying"):
                rows, people = await classified_rows(client, session["session_key"], teams, constructor_names)
            else:
                rows, people = await session_rows(client, session["session_key"], constructor_names, teams)
            if len(rows) < 10:
                self._unavailable.add((race_id, session_type))
                continue
            await db.store_drivers(people, rename=False)
            await db.store_race_results(race_id, rows, session_type)
            report.sessions.append(f"{race_id} {session_type}")

    # ---- 4. preseason testing -----------------------------------------------------------------

    async def _testing(self, db, client, races, now: datetime, report: Report) -> None:
        years = range(FIRST_OPENF1, now.year + 1)
        have = await preseason_testing.load_stored(db, years)
        for year in years:
            if year in have or ("testing", year) in self._unavailable:
                continue
            first_race = min((d for r in races.values() if r["year"] == year and (d := _race_day(r))), default=None)
            if year == now.year and (first_race is None or now.date() < first_race):
                continue                      # still running: the loop's testing refresh keeps it current
            testing = await preseason_testing.from_openf1(client, year, now)
            if not testing:
                self._unavailable.add(("testing", year))
                continue
            await preseason_testing.store(db, testing)
            report.testing.append(year)

    # ---- 5. weather ---------------------------------------------------------------------------

    async def _weather(self, db, races, stored, report: Report) -> None:
        from services.session_replay import session_key
        have = {r["session_type"] for r in await db._run_query(
            "SELECT session_type FROM prediction_cache WHERE circuit_name = '_weather'")}
        todo = []
        for (race_id, session_type) in stored:
            race = races.get(race_id)
            if race is None or race["year"] < FIRST_OPENF1 or session_type not in CODES:
                continue
            gp = race.get("gp") or race_id
            if "|".join(map(str, session_key(race["year"], gp, CODES[session_type]))) in have:
                continue
            if (race_id, f"weather {session_type}") not in self._unavailable:
                todo.append((race, gp, session_type))
        for race, gp, session_type in sorted(todo, key=lambda t: (-t[0]["year"], -int(t[0]["round"])))[:WEATHER_BATCH]:
            try:
                _, readings = await self.load_weather(race["year"], gp, CODES[session_type])
            except OpenF1Locked:
                raise
            except Exception:
                readings = []
            if readings:
                report.weather.append(f"{race['race_id']} {session_type}")
            else:
                self._unavailable.add((race["race_id"], f"weather {session_type}"))

    # ---- 6. the title race's track record -----------------------------------------------------

    async def _title_backtest(self, db, races, today: date, report: Report) -> None:
        seasons = sorted({r["year"] for r in races.values()})
        finished = {y for y in seasons if y < today.year}
        cached = (await db.get_prediction_cache("_championship", "backtest") or {}).get("result", {})
        considered = set(cached.get("seasons_considered") or [s["year"] for s in cached.get("seasons", [])])
        outdated = bool(cached.get("seasons")) and self.title_backtest_version is not None             and cached.get("method_version") != self.title_backtest_version
        if not outdated and not finished - considered - {min(seasons, default=0)}:
            return
        if await self.rebuild_title_backtest(sorted(finished)):
            report.title_backtest = True


def _race_day(race: Dict[str, Any]) -> Optional[date]:
    try:
        return date.fromisoformat(str(race.get("date") or "")[:10])
    except ValueError:
        return None
