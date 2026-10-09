"""
Who's actually entered for a race weekend, so predictions cover the right drivers.

Predictions used to cover whoever raced last time, which leaves out a driver returning from injury
(Hadjar qualified 4th at Baku 2026 and wasn't predicted) and keeps one who's out. The line-up comes
from, in order:

1. sessions of that weekend already stored — qualifying first; FP1 only as a last resort, since
   rookies often stand in for regular drivers there;
2. OpenF1's driver list for the weekend's latest session that has started (free — but OpenF1 shuts
   free access while a session is live, and then this step is skipped);
3. nothing: the caller falls back to the last race's line-up and says so.
"""
import logging
import time
import unicodedata
from dataclasses import dataclass, field as dc_field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from services.driver_names import tidy_full_name
from services.openf1_live import OpenF1Client, OpenF1Locked, parse_time
from services.weekend_practice import team_id_for

logger = logging.getLogger(__name__)

# Stored sessions to take the line-up from, best first.
STORED_SESSIONS = [("qualifying", "qualifying"), ("sprint_qualifying", "sprint qualifying"), ("fp3", "practice 3"),
                   ("fp2", "practice 2"), ("sprint", "sprint"), ("race", "race"), ("fp1", "practice 1")]
MIN_FIELD = 15            # fewer rows than this isn't a whole field
CACHE_SECONDS = 600


def _norm(text: Optional[str]) -> str:
    text = "".join(c for c in unicodedata.normalize("NFD", text or "") if not unicodedata.combining(c))
    return " ".join(text.replace("_", " ").casefold().replace(" f1 team", "").split())


@dataclass
class Field:
    teams: Dict[str, Optional[str]]              # driver_id -> constructor_id (None: their last team)
    source: str                                  # shown on the page: "this weekend's qualifying"
    names: Dict[str, str] = dc_field(default_factory=dict)


class EntryListService:
    def __init__(self, client_factory: Callable[[], OpenF1Client] = lambda: OpenF1Client(creds={})):
        self._client: Optional[OpenF1Client] = None
        self._client_factory = client_factory
        self._cache: Dict[tuple, tuple] = {}

    @property
    def client(self) -> OpenF1Client:
        if self._client is None:
            self._client = self._client_factory()
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()

    async def field(self, db, circuit: str, year: int, constructor_names: Dict[str, str]) -> Optional[Field]:
        """The weekend's line-up at `circuit`, or None when nothing says who's entered yet.
        `constructor_names` (constructor_id -> name) maps OpenF1's team names onto our ids."""
        key = (year, _norm(circuit))
        hit = self._cache.get(key)
        if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
            return hit[1]
        found = await self._from_database(db, circuit, year)
        if found is None or any(team is None for team in found.teams.values()):
            # Stored practice rows can lack the team (FastF1 doesn't always have it yet): OpenF1's
            # entry list names each driver's car — Lawson back at Racing Bulls, not his last seat.
            openf1 = await self._from_openf1(circuit, year, constructor_names)
            if found is None:
                found = openf1
            elif openf1 is not None:
                found.teams = {d: t or openf1.teams.get(d) for d, t in found.teams.items()}
                found.names = {**openf1.names, **found.names}
        self._cache[key] = (time.monotonic(), found)
        return found

    async def _from_database(self, db, circuit: str, year: int) -> Optional[Field]:
        try:
            races = await db.get_races_by_year(year)
        except Exception:
            return None
        race = next((r for r in races if _norm(r.get("circuit_name")) == _norm(circuit)), None)
        if race is None:
            return None
        for session_type, label in STORED_SESSIONS:
            try:
                rows = await db.get_race_results(race["race_id"], session_type)
            except Exception:
                continue
            if len(rows) >= MIN_FIELD:
                return Field({r["driver_id"]: r.get("constructor_id") or None for r in rows if r.get("driver_id")},
                             f"this weekend's {label}")
        return None

    async def _from_openf1(self, circuit: str, year: int, constructor_names: Dict[str, str]) -> Optional[Field]:
        try:
            meetings = await self.client.get("meetings", year=year)
            wanted = _norm(circuit)
            now = datetime.now(timezone.utc)
            candidates = [m for m in meetings if wanted in (_norm(m.get("location")), _norm(m.get("circuit_short_name")))]
            if not candidates:
                return None
            # The nearest weekend to now at that circuit (a circuit can host two rounds in a season).
            meeting = min(candidates, key=lambda m: abs(((parse_time(m.get("date_start")) or now) - now).total_seconds()))
            sessions = await self.client.get("sessions", meeting_key=meeting["meeting_key"])
            started = [s for s in sessions if (parse_time(s.get("date_start")) or now) <= now and not s.get("is_cancelled")]
            if not started:
                return None
            # The latest session that has started, preferring anything but Practice 1 (stand-ins).
            started.sort(key=lambda s: s["date_start"], reverse=True)
            session = next((s for s in started if s.get("session_name") != "Practice 1"), started[0])
            drivers = await self.client.get("drivers", session_key=session["session_key"])
        except OpenF1Locked:
            return None
        except Exception as exc:
            logger.warning("entry list for %s %s: %s", year, circuit, exc)
            return None
        if len(drivers) < MIN_FIELD:
            return None
        teams = {d["name_acronym"].lower(): team_id_for(d.get("team_name"), constructor_names)
                 for d in drivers if d.get("name_acronym")}
        names = {d["name_acronym"].lower(): tidy_full_name(d["full_name"]) for d in drivers
                 if d.get("name_acronym") and d.get("full_name")}
        return Field(teams, f"the {session.get('session_name', 'session').lower()} entry list", names)
