"""
OpenF1 as the live-timing source (https://openf1.org).

OpenF1 serves every session's laps, tyre stints, pit stops, positions, gaps and race-control
messages. Finished sessions are free; data *during* a session needs their paid tier (credentials
in OPENF1_USERNAME / OPENF1_PASSWORD, exchanged for a bearer token at /token). The same code path
serves both: a live session is read up to "now", a finished one can be replayed up to a moving
clock — which is how the pipeline is tested without a subscription.

OpenF1's records are turned into the FastF1-shaped laps table that services/timing_board.py builds
the board from, so every source produces the same rows. OpenF1 adds real gaps/intervals (the FastF1
path only estimated them from lap times) and the track status from race control.
"""
import asyncio
import logging
import os
import time
import unicodedata
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx
import pandas as pd

from services.timing_board import build_classified_positions, build_timed_positions, is_timed_session

logger = logging.getLogger(__name__)

BASE_URL = "https://api.openf1.org"
FREE_PER_MINUTE = 30       # OpenF1 free tier: 3 requests/second, 30/minute
SPONSOR_PER_MINUTE = 60    # paid tier: 6/second, 60/minute

STOPPED_AFTER_SECONDS = 300

# Our session codes -> OpenF1 session_name (sprint qualifying was "Sprint Shootout" in 2023).
SESSION_NAMES = {
    "FP1": ("Practice 1",), "FP2": ("Practice 2",), "FP3": ("Practice 3",),
    "SQ": ("Sprint Qualifying", "Sprint Shootout"), "S": ("Sprint",), "Q": ("Qualifying",), "R": ("Race",),
}
CODE_FOR_NAME = {name: code for code, names in SESSION_NAMES.items() for name in names}


class OpenF1Locked(Exception):
    """OpenF1 shuts free access — past sessions included — while an F1 session is live."""


def credentials() -> Optional[Dict[str, str]]:
    user, password = os.getenv("OPENF1_USERNAME"), os.getenv("OPENF1_PASSWORD")
    return {"username": user, "password": password} if user and password else None


def parse_time(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    ts = pd.Timestamp(value)
    return (ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")).to_pydatetime()


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c)).replace("_", " ").casefold().strip()


class OpenF1Client:
    """Async OpenF1 client: throttled to the tier's per-minute limit, retries 429s, and adds the
    bearer token when credentials are configured."""

    def __init__(self, creds: Optional[Dict[str, str]] = None, per_minute: Optional[int] = None,
                 transport: Optional[httpx.AsyncBaseTransport] = None):
        self.creds = creds if creds is not None else credentials()
        self.per_minute = per_minute or (SPONSOR_PER_MINUTE if self.creds else FREE_PER_MINUTE)
        self._http = httpx.AsyncClient(base_url=BASE_URL, timeout=30, transport=transport)
        self.per_second = max(1, self.per_minute // 10)   # 3 free, 6 paid
        self._lock = asyncio.Lock()
        self._sent: deque = deque()   # request times in the last minute
        self._token: Optional[str] = None
        self._token_expires = 0.0

    @property
    def authenticated(self) -> bool:
        return bool(self.creds)

    async def close(self) -> None:
        await self._http.aclose()

    async def _auth_header(self) -> Dict[str, str]:
        if not self.creds:
            return {}
        if not self._token or time.monotonic() > self._token_expires:
            r = await self._http.post("/token", data=self.creds)
            r.raise_for_status()
            body = r.json()
            self._token = body["access_token"]
            self._token_expires = time.monotonic() + float(body.get("expires_in", 3600)) - 60
        return {"Authorization": f"Bearer {self._token}"}

    async def _wait_for_slot(self) -> None:
        """Wait until another request fits both limits (per second and per minute)."""
        while True:
            now = time.monotonic()
            while self._sent and now - self._sent[0] >= 60:
                self._sent.popleft()
            last_second = [t for t in self._sent if now - t < 1]
            if len(self._sent) < self.per_minute and len(last_second) < self.per_second:
                self._sent.append(now)
                return
            wait = (self._sent[0] + 60 if len(self._sent) >= self.per_minute else last_second[0] + 1) - now
            await asyncio.sleep(max(0.05, wait))

    async def get(self, endpoint: str, **filters: Any) -> List[Dict[str, Any]]:
        """GET /v1/{endpoint}. Filter names may carry OpenF1's comparison operators:
        get("position", session_key=1, **{"date>": "2026-..."}) -> ?session_key=1&date>2026-..."""
        query = "&".join(
            f"{name}{'' if name[-1] in '<>=' else '='}{quote(str(value), safe=':+-.')}"
            for name, value in filters.items()
        )
        url = f"/v1/{endpoint}" + (f"?{query}" if query else "")
        for attempt in range(5):
            async with self._lock:   # stay inside the tier's per-second and per-minute limits
                await self._wait_for_slot()
            r = await self._http.get(url, headers=await self._auth_header())
            if r.status_code == 429:
                await asyncio.sleep(2 ** attempt)
                continue
            if r.status_code == 404:   # OpenF1 answers "No results found." with a 404
                return []
            if r.status_code == 401 and "session in progress" in r.text.lower():
                raise OpenF1Locked(r.json().get("detail", "Live F1 session in progress"))
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, list) else []
        raise RuntimeError(f"OpenF1 kept rate-limiting {endpoint}")


async def find_session(client: OpenF1Client, year: int, gp: str, code: str) -> Optional[Dict[str, Any]]:
    """The OpenF1 session for one of our sessions. `gp` is the schedule's race name ("Spanish
    Grand Prix", or the id form "Spanish_Grand_Prix"); OpenF1 uses the same meeting names."""
    meetings = await client.get("meetings", year=year)
    wanted = _norm(gp)
    meeting = next((m for m in meetings if _norm(m.get("meeting_name", "")) == wanted), None)
    if meeting is None:
        token = wanted.replace(" grand prix", "")
        meeting = next((m for m in meetings if token and token in _norm(m.get("meeting_name", ""))), None)
    if meeting is None:
        return None
    sessions = await client.get("sessions", meeting_key=meeting["meeting_key"])
    names = SESSION_NAMES.get(code, ())
    session = next((s for s in sessions if s.get("session_name") in names), None)
    return {**session, "meeting_name": meeting.get("meeting_name")} if session else None


# ---------------------------------------------------------------------------
# One session's records
# ---------------------------------------------------------------------------

class SessionFeed:
    """Everything OpenF1 has for a session, refreshed incrementally while it's live."""

    ENDPOINTS = ("drivers", "laps", "stints", "pit", "position", "intervals", "race_control", "weather")
    INCREMENTAL = {"position": "date", "intervals": "date", "race_control": "date", "weather": "date"}

    def __init__(self, client: OpenF1Client, session: Dict[str, Any]):
        self.client = client
        self.session = session
        self.key = session["session_key"]
        self.data: Dict[str, List[Dict[str, Any]]] = {name: [] for name in self.ENDPOINTS}

    async def load_all(self) -> None:
        for name in self.ENDPOINTS:
            self.data[name] = await self.client.get(name, session_key=self.key)

    async def refresh(self) -> None:
        """Laps are re-read whole (a lap's row appears when it starts and is completed later);
        the streams that only grow are fetched from the newest record already held."""
        if not self.data["drivers"]:
            self.data["drivers"] = await self.client.get("drivers", session_key=self.key)
        for name in ("laps", "stints", "pit"):
            self.data[name] = await self.client.get(name, session_key=self.key)
        for name, field in self.INCREMENTAL.items():
            have = self.data[name]
            if not have:
                self.data[name] = await self.client.get(name, session_key=self.key)
                continue
            since = max(r[field] for r in have if r.get(field))
            new = await self.client.get(name, session_key=self.key, **{f"{field}>": since})
            self.data[name] = have + new


# ---------------------------------------------------------------------------
# Records -> timing board
# ---------------------------------------------------------------------------

def _before(records: List[Dict[str, Any]], clock: Optional[datetime], field: str = "date") -> List[Dict[str, Any]]:
    if clock is None:
        return records
    return [r for r in records if (t := parse_time(r.get(field))) is not None and t <= clock]


_DURATION_COLUMNS = ("LapTime", "Sector1Time", "Sector2Time", "Sector3Time", "PitInTime")


def _durations(frame: pd.DataFrame) -> None:
    """Make the time columns timedeltas (an all-empty column comes out as datetime NaT)."""
    for c in _DURATION_COLUMNS:
        column = frame[c]
        frame[c] = (pd.Series(pd.NaT, index=frame.index, dtype="timedelta64[ns]")
                    if column.isna().all() else pd.to_timedelta(column))


def laps_frame(data: Dict[str, List[Dict[str, Any]]], clock: Optional[datetime] = None) -> pd.DataFrame:
    """The FastF1-shaped laps table the board is built from, as of `clock` (None: everything).
    A lap counts once it's finished; every driver gets at least a placeholder row, so drivers
    who haven't set a time are listed ("No time") rather than missing."""
    acronym = {d["driver_number"]: d.get("name_acronym") or str(d["driver_number"]) for d in data.get("drivers", [])}
    stints: Dict[int, List[Dict[str, Any]]] = {}
    for s in data.get("stints", []):
        stints.setdefault(s["driver_number"], []).append(s)
    pits: Dict[int, List[Dict[str, Any]]] = {}
    for p in _before(data.get("pit", []), clock):
        pits.setdefault(p["driver_number"], []).append(p)
    latest_position: Dict[int, int] = {}
    for p in sorted(_before(data.get("position", []), clock), key=lambda r: r["date"]):
        latest_position[p["driver_number"]] = p["position"]

    rows = []
    for lap in data.get("laps", []):
        start, duration = parse_time(lap.get("date_start")), lap.get("lap_duration")
        if clock is not None and (start is None or duration is None or start + timedelta(seconds=duration) > clock):
            continue   # not finished yet at this point
        number = lap["driver_number"]
        stint = next((s for s in stints.get(number, [])
                      if (s.get("lap_start") or 0) <= lap["lap_number"] <= (s.get("lap_end") or 10_000)), None)
        rows.append({
            "Driver": acronym.get(number, str(number)),
            "DriverNumber": number,
            "LapNumber": lap["lap_number"],
            "LapTime": pd.to_timedelta(duration, unit="s") if duration is not None else pd.NaT,
            **{f"Sector{i}Time": (pd.to_timedelta(lap[f"duration_sector_{i}"], unit="s")
                                  if lap.get(f"duration_sector_{i}") is not None else pd.NaT) for i in (1, 2, 3)},
            "Compound": stint.get("compound") if stint else None,
            "TyreLife": (stint.get("tyre_age_at_start") or 0) + lap["lap_number"] - stint["lap_start"] + 1
                        if stint and stint.get("lap_start") is not None else None,
            "Stint": stint.get("stint_number") if stint else None,
            "PitInTime": pd.NaT,
            "Position": None,
            "LapEnd": start + timedelta(seconds=duration) if start and duration is not None else None,
        })
    frame = pd.DataFrame(rows, columns=["Driver", "DriverNumber", "LapNumber", "LapTime", "Sector1Time",
                                        "Sector2Time", "Sector3Time", "Compound", "TyreLife", "Stint",
                                        "PitInTime", "Position", "LapEnd"])
    _durations(frame)

    # Placeholders for drivers without a finished lap, then the per-driver "now" values on each
    # driver's last row: race position and whether they're in the pit lane at this moment.
    missing = [n for n in acronym if n not in set(frame["DriverNumber"])]
    if missing:
        frame = pd.concat([frame, pd.DataFrame([{"Driver": acronym[n], "DriverNumber": n} for n in missing])],
                          ignore_index=True)
        _durations(frame)
    now = clock or datetime.now(timezone.utc)
    for number, idx in frame.groupby("DriverNumber")["LapNumber"].apply(
            lambda s: s.fillna(-1).idxmax()).items():
        frame.at[idx, "Position"] = latest_position.get(number)
        for p in pits.get(number, []):
            entered = parse_time(p.get("date"))
            lane = p.get("lane_duration") or p.get("pit_duration") or 0
            if entered and entered <= now <= entered + timedelta(seconds=float(lane) + 5):
                frame.at[idx, "PitInTime"] = pd.Timedelta(0)
    return frame


def weather_at(records: List[Dict[str, Any]], clock: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    """The track's weather at `clock` (the latest reading up to then; the first one before the
    session's first reading): air/track temperature (°C), humidity (%), wind speed (km/h — OpenF1
    gives m/s) and direction (degrees, where it blows from), pressure (mbar) and whether it's raining."""
    readings = sorted((r for r in records if r.get("date")), key=lambda r: r["date"])
    if not readings:
        return None
    upto = _before(readings, clock) if clock is not None else readings
    r = upto[-1] if upto else readings[0]
    wind = r.get("wind_speed")
    return {
        "date": r["date"],
        "air_temperature": r.get("air_temperature"),
        "track_temperature": r.get("track_temperature"),
        "humidity": r.get("humidity"),
        "wind_speed_kmh": round(float(wind) * 3.6, 1) if wind is not None else None,
        "wind_direction": r.get("wind_direction"),
        "pressure": r.get("pressure"),
        "rain": bool(r.get("rainfall")),
    }


def weather_summary(records: List[Dict[str, Any]], start: Optional[datetime], end: Optional[datetime]) -> Optional[Dict[str, Any]]:
    """Conditions at the start of a session and how they ranged over it."""
    during = [r for r in records if r.get("date") and (start is None or parse_time(r["date"]) >= start)
              and (end is None or parse_time(r["date"]) <= end)] or records
    if not during:
        return None

    def span(field):
        values = [r[field] for r in during if r.get(field) is not None]
        return [min(values), max(values)] if values else None

    return {
        "at_start": weather_at(records, start),
        "rain_during": any(r.get("rainfall") for r in during),
        "air_range": span("air_temperature"),
        "track_range": span("track_temperature"),
        "readings": len(during),
    }


def _format_gap(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return f"+{value:.3f}"
    text = str(value).strip()
    return text if text.startswith("+") else f"+{text}"


def track_status(race_control: List[Dict[str, Any]]) -> str:
    """Track-wide state from race control: green, yellow (whole track), sc, vsc, red or chequered.
    Sector yellows and blue flags don't change it."""
    status = "green"
    for m in sorted(race_control, key=lambda r: r.get("date") or ""):
        message = (m.get("message") or "").upper()
        flag = (m.get("flag") or "").upper()
        if m.get("category") == "SafetyCar":
            if "DEPLOYED" in message:
                status = "vsc" if "VIRTUAL" in message else "sc"
            elif "ENDING" in message and status == "vsc":
                status = "green"
        elif m.get("category") == "Flag" and (m.get("scope") in (None, "Track")):
            status = {"GREEN": "green", "CLEAR": "green", "RED": "red", "CHEQUERED": "chequered",
                      "YELLOW": "yellow", "DOUBLE YELLOW": "yellow"}.get(flag, status)
    return status


def build_state(data: Dict[str, List[Dict[str, Any]]], session: Dict[str, Any], code: str, race_id: str,
                clock: Optional[datetime] = None, replay: bool = False) -> Dict[str, Any]:
    """The LiveState the API streams, in the same shape as the FastF1 poller's."""
    teams = {d.get("name_acronym"): d.get("team_name") for d in data.get("drivers", [])}
    frame = laps_frame(data, clock)
    race_control = _before(data.get("race_control", []), clock)
    status = track_status(race_control)
    now = clock or datetime.now(timezone.utc)
    end = parse_time(session.get("date_end"))
    finished = status == "chequered" and (not is_timed_session(code) or (end is not None and now >= end))
    state: Dict[str, Any] = {
        "race_id": race_id,
        "session": code,
        "source": "openf1",
        "replay": replay,
        "clock": now.isoformat(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_status": "finished" if finished else "live",
        "track_status": status,
        "weather": weather_at(data.get("weather", []), clock),
    }
    if is_timed_session(code):
        positions = build_timed_positions(frame, teams)
        state.update({"session_type": "timed", "positions": positions})
    else:
        positions = build_classified_positions(frame, teams)
        latest: Dict[int, Dict[str, Any]] = {}
        for r in sorted(_before(data.get("intervals", []), clock), key=lambda r: r["date"]):
            latest[r["driver_number"]] = r
        number = {d.get("name_acronym"): d["driver_number"] for d in data.get("drivers", [])}
        chequered = [parse_time(m["date"]) for m in race_control
                     if (m.get("flag") or "").upper() == "CHEQUERED" and m.get("date")]
        reference = min(chequered) if status == "chequered" and chequered else now
        for i, row in enumerate(positions):
            iv = latest.get(number.get(row["driver_id"]), {})
            row["gap"] = None if i == 0 else _format_gap(iv.get("gap_to_leader")) or row["gap"]
            row["interval"] = None if i == 0 else _format_gap(iv.get("interval"))
            # OpenF1 has no retirement status: a car that hadn't finished a lap for a while before
            # "now" (or before the chequered flag, once it's out) has stopped. Not under a red flag.
            ended = frame.loc[frame["Driver"] == row["driver_id"], "LapEnd"].dropna()
            if (status != "red" and not ended.empty
                    and reference - max(ended) > timedelta(seconds=STOPPED_AFTER_SECONDS)):
                row.update(status="Stopped", gap=None, interval=None)   # its last gap is stale
        completed = frame["LapNumber"].dropna()
        state.update({"session_type": "classified", "positions": positions,
                      "lap": int(completed.max()) if not completed.empty else 0, "total_laps": None})
    state["leader"] = positions[0]["driver_id"] if positions else None
    return state
