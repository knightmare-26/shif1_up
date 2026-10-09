"""
Weather and replays of finished sessions, for the Race Results page.

Both come from OpenF1, whose data for finished sessions is free (2023 onwards) — except while an F1
session is live, when OpenF1 shuts free access to everything, past sessions included. So:

- **Weather** is kept in the database once fetched (prediction_cache, circuit_name "_weather";
  scripts/backfill_weather.py preloads every session), and served from there — the panel works
  during a live session too.
- **Penalties** (the stewards' race-control messages, services/penalties.py) are kept the same way
  (circuit_name "_penalties"), stored even when a session had none so they're fetched only once.
- **Replays** need the whole session (laps, stints, pit stops, positions, gaps, race control,
  weather — a race's gap data alone is ~27k rows), so they're loaded when someone presses play and
  kept in memory only. During a live session they're unavailable (`OpenF1Locked`).

The board is built by the same code as live timing (openf1_live.build_state), so a replay looks
exactly like live.
"""
import asyncio
import logging
import unicodedata
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from services.openf1_live import OpenF1Client, SessionFeed, build_state, find_session, parse_time, weather_summary
from services.timing_board import build_race_id

logger = logging.getLogger(__name__)

FIRST_OPENF1_SEASON = 2023
MAX_FEEDS = 4                   # whole sessions kept in memory
REPLAY_TAIL_SECONDS = 10 * 60   # keep playing a little past the scheduled end (the flag, the in-lap)
WEATHER_CACHE = "_weather"      # prediction_cache.circuit_name for stored weather
PENALTIES_CACHE = "_penalties"  # ... and for a session's stewards' messages
WEATHER_FIELDS = ("date", "air_temperature", "track_temperature", "humidity", "wind_speed",
                  "wind_direction", "rainfall", "pressure")

Key = Tuple[int, str, str]


class ReplayUnavailable(Exception):
    """This session can't be shown (too old, not run yet, or unknown to OpenF1)."""


def session_key(year: int, gp: str, code: str) -> Key:
    """"Spanish Grand Prix", "Spanish_Grand_Prix" and "spanish" are the same weekend."""
    text = "".join(c for c in unicodedata.normalize("NFD", gp) if not unicodedata.combining(c))
    return year, text.replace("_", " ").casefold().replace(" grand prix", "").strip(), code


def _compact(readings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [{k: r.get(k) for k in WEATHER_FIELDS} for r in readings]


class SessionReplayService:
    def __init__(self, db_getter: Callable[[], Any] = lambda: None,
                 client_factory: Callable[[], OpenF1Client] = lambda: OpenF1Client(creds={})):
        # Only free historical data is needed here, so never use (or spend) the paid tier.
        self._db = db_getter
        self._client: Optional[OpenF1Client] = None
        self._client_factory = client_factory
        self._sessions: Dict[Key, Dict[str, Any]] = {}
        self._weather: Dict[Key, List[Dict[str, Any]]] = {}
        self._penalties: Dict[Key, List[Dict[str, Any]]] = {}
        self._feeds: "OrderedDict[Key, SessionFeed]" = OrderedDict()
        self._locks: Dict[tuple, asyncio.Lock] = {}

    @property
    def client(self) -> OpenF1Client:
        if self._client is None:
            self._client = self._client_factory()
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()

    def _lock(self, purpose: str, key: Key) -> asyncio.Lock:
        """One lock per kind of load per session (they nest: the weather load looks the session up)."""
        return self._locks.setdefault((purpose, *key), asyncio.Lock())

    @staticmethod
    def _check_finished(session: Dict[str, Any]) -> None:
        end = parse_time(session.get("date_end"))
        if end is None or end > datetime.now(timezone.utc):
            raise ReplayUnavailable("Available once the session has finished")

    async def session(self, year: int, gp: str, code: str) -> Dict[str, Any]:
        if year < FIRST_OPENF1_SEASON:
            raise ReplayUnavailable(f"Session data starts in {FIRST_OPENF1_SEASON}")
        key = session_key(year, gp, code)
        if key not in self._sessions:
            async with self._lock("session", key):
                if key not in self._sessions:
                    found = await find_session(self.client, year, gp, code)
                    if found is None:
                        raise ReplayUnavailable("No data for this session")
                    self._sessions[key] = found
        self._check_finished(self._sessions[key])
        return self._sessions[key]

    # ---- weather ------------------------------------------------------------------------

    async def _stored_weather(self, key: Key) -> Optional[Dict[str, Any]]:
        db = self._db()
        if db is None:
            return None
        try:
            row = await db.get_prediction_cache(WEATHER_CACHE, "|".join(map(str, key)))
        except Exception:
            return None
        return row["result"] if row and row.get("result", {}).get("session") else None

    async def _store_weather(self, key: Key, session: Dict[str, Any], readings: List[Dict[str, Any]]) -> None:
        db = self._db()
        if db is None:
            return
        try:
            await db.set_prediction_cache(WEATHER_CACHE, "|".join(map(str, key)), "",
                                          {"session": session, "readings": readings})
        except Exception as exc:
            logger.warning("couldn't store weather for %s: %s", key, exc)

    async def load_weather(self, year: int, gp: str, code: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """(session, readings): memory, then the database, then OpenF1 (and stored for next time)."""
        key = session_key(year, gp, code)
        if year < FIRST_OPENF1_SEASON:
            raise ReplayUnavailable(f"Session data starts in {FIRST_OPENF1_SEASON}")
        if key not in self._weather:
            async with self._lock("weather", key):
                if key not in self._weather:
                    stored = await self._stored_weather(key)
                    if stored:
                        self._sessions.setdefault(key, stored["session"])
                        self._weather[key] = stored["readings"]
                    else:
                        session = await self.session(year, gp, code)
                        readings = _compact(await self.client.get("weather", session_key=session["session_key"]))
                        self._weather[key] = readings
                        if readings:
                            await self._store_weather(key, session, readings)
        session = self._sessions[key]
        self._check_finished(session)
        return session, self._weather[key]

    async def weather(self, year: int, gp: str, code: str) -> Dict[str, Any]:
        """Conditions at the start and over the session, plus how long a replay runs."""
        session, readings = await self.load_weather(year, gp, code)
        start, end = parse_time(session["date_start"]), parse_time(session["date_end"])
        return {
            "year": year, "gp": gp, "session": code,
            "session_name": session.get("session_name"),
            "meeting_name": session.get("meeting_name"),
            "start": session["date_start"], "end": session["date_end"],
            "duration_seconds": int((end - start).total_seconds()) + REPLAY_TAIL_SECONDS,
            "weather": weather_summary(readings, start, end),
        }

    # ---- penalties ----------------------------------------------------------------------

    async def load_penalties(self, year: int, gp: str, code: str) -> List[Dict[str, Any]]:
        """The session's stewards' messages (services/penalties.relevant): memory, then the database,
        then OpenF1 — stored even when there were none, so a quiet session isn't fetched again."""
        from services.penalties import relevant
        key = session_key(year, gp, code)
        if year < FIRST_OPENF1_SEASON:
            raise ReplayUnavailable(f"Session data starts in {FIRST_OPENF1_SEASON}")
        if key not in self._penalties:
            async with self._lock("penalties", key):
                if key not in self._penalties:
                    db = self._db()
                    stored = None
                    if db is not None:
                        try:
                            stored = await db.get_prediction_cache(PENALTIES_CACHE, "|".join(map(str, key)))
                        except Exception:
                            stored = None
                    if stored and "messages" in (stored.get("result") or {}):
                        self._penalties[key] = stored["result"]["messages"]
                    else:
                        session = await self.session(year, gp, code)
                        messages = relevant(await self.client.get("race_control", session_key=session["session_key"]))
                        self._penalties[key] = messages
                        if db is not None:
                            try:
                                await db.set_prediction_cache(PENALTIES_CACHE, "|".join(map(str, key)), "",
                                                              {"messages": messages})
                            except Exception as exc:
                                logger.warning("couldn't store penalties for %s: %s", key, exc)
        return self._penalties[key]

    # ---- replay -------------------------------------------------------------------------

    async def _feed(self, year: int, gp: str, code: str) -> Tuple[Dict[str, Any], SessionFeed]:
        session = await self.session(year, gp, code)
        key = session_key(year, gp, code)
        if key not in self._feeds:
            async with self._lock("feed", key):
                if key not in self._feeds:
                    feed = SessionFeed(self.client, session)
                    await feed.load_all()
                    self._feeds[key] = feed
                    while len(self._feeds) > MAX_FEEDS:
                        self._feeds.popitem(last=False)
        self._feeds.move_to_end(key)
        return session, self._feeds[key]

    async def frame(self, year: int, gp: str, code: str, seconds: float) -> Dict[str, Any]:
        """The timing board, with the weather, `seconds` into the session."""
        session, feed = await self._feed(year, gp, code)
        clock = parse_time(session["date_start"]) + timedelta(seconds=max(0.0, seconds))
        # build_state is pandas work on up to ~30k records: keep it off the event loop.
        state = await asyncio.to_thread(build_state, feed.data, session, code,
                                        build_race_id(year, gp.replace("_", " "), code), clock, True)
        return {"seconds": seconds, "state": state}
