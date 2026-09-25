"""
Live relays: the API follows sessions on OpenF1 itself and streams them through Redis to the Live
pages — no separate poller process (Render's free plan has no free background worker).

- A **live** relay reads the session up to "now". It needs OpenF1's paid tier (OPENF1_USERNAME /
  OPENF1_PASSWORD); with credentials set, `LiveRelayManager.schedule_loop` starts one for every
  session on the calendar as it begins, and when a race-like session finishes it runs the usual
  post-session ingest.
- A **replay** relay plays a finished session back against a moving clock (free, no credentials):
  the whole session is loaded once and the board is rebuilt as the clock advances. Admins start
  them from the Data Manager; they're how the pipeline is checked without a subscription.

Relays write the same LiveState (and race ids) as the FastF1 poller, so the pages don't care
which one is running.
"""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

from services.openf1_live import (
    CODE_FOR_NAME, OpenF1Client, SessionFeed, build_state, credentials, find_session, parse_time,
)
from services.timing_board import build_race_id

logger = logging.getLogger(__name__)

LIVE_POLL_SECONDS = 8          # 7 requests a poll fits the paid tier's 60/minute
REPLAY_TICK_SECONDS = 3        # a replay re-reads nothing, so it can update often
FINISHED_LINGER_SECONDS = 600  # keep publishing the final board for a while after the flag
SCHEDULE_CHECK_SECONDS = 120
STATE_TTL_SECONDS = 3600

_sleep = asyncio.sleep   # patched out in tests


@dataclass
class Relay:
    race_id: str
    year: int
    gp: str
    session: str
    replay_speed: Optional[float]          # None: live
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = "starting"               # starting | running | finished | failed | stopped
    detail: Optional[str] = None
    clock: Optional[str] = None
    task: Optional[asyncio.Task] = None

    def summary(self) -> Dict[str, Any]:
        return {"race_id": self.race_id, "year": self.year, "gp": self.gp, "session": self.session,
                "replay": self.replay_speed is not None, "replay_speed": self.replay_speed,
                "status": self.status, "detail": self.detail, "clock": self.clock, "started_at": self.started_at}


class LiveRelayManager:
    def __init__(self, redis_getter: Callable[[], Any],
                 on_session_finished: Optional[Callable[[int, str, str], Awaitable[None]]] = None,
                 client_factory: Callable[[], OpenF1Client] = OpenF1Client):
        self._redis = redis_getter
        self._on_finished = on_session_finished
        self._client_factory = client_factory
        self.relays: Dict[str, Relay] = {}

    @staticmethod
    def live_available() -> bool:
        """Live (not replay) data needs OpenF1 credentials."""
        return credentials() is not None

    def running(self) -> List[Relay]:
        return [r for r in self.relays.values() if r.status in ("starting", "running")]

    def start(self, year: int, gp: str, session: str, replay_speed: Optional[float] = None) -> Relay:
        race_id = build_race_id(year, gp, session)
        current = self.relays.get(race_id)
        if current and current.status in ("starting", "running"):
            return current
        relay = Relay(race_id, year, gp, session, replay_speed)
        relay.task = asyncio.create_task(self._run(relay), name=f"live-relay-{race_id}")
        self.relays[race_id] = relay
        return relay

    async def stop(self, race_id: str) -> bool:
        relay = self.relays.get(race_id)
        if not relay or not relay.task or relay.task.done():
            return False
        relay.task.cancel()
        await asyncio.gather(relay.task, return_exceptions=True)
        relay.status = "stopped"
        return True

    async def stop_all(self) -> None:
        for race_id in list(self.relays):
            await self.stop(race_id)

    async def _publish(self, state: Dict[str, Any]) -> None:
        redis = self._redis()
        await redis.set_live_state(state["race_id"], state, ttl=STATE_TTL_SECONDS)
        await redis.publish_update(state["race_id"], {"type": "state_update", "state": state})

    async def _run(self, relay: Relay) -> None:
        client = self._client_factory()
        try:
            session = await find_session(client, relay.year, relay.gp, relay.session)
            if session is None:
                relay.status, relay.detail = "failed", "OpenF1 has no such session"
                return
            feed = SessionFeed(client, session)
            relay.status = "running"
            if relay.replay_speed is not None:
                await self._replay(relay, feed, session)
            else:
                await self._live(relay, feed, session)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("live relay %s failed", relay.race_id)
            relay.status, relay.detail = "failed", str(exc)[:200]
        finally:
            await client.close()

    async def _replay(self, relay: Relay, feed: SessionFeed, session: Dict[str, Any]) -> None:
        await feed.load_all()
        clock = parse_time(session["date_start"]) - timedelta(minutes=1)
        end = parse_time(session["date_end"]) + timedelta(minutes=15)
        finished_at = None
        while clock <= end:
            state = build_state(feed.data, session, relay.session, relay.race_id, clock=clock, replay=True)
            await self._publish(state)
            relay.clock = clock.isoformat()
            if state["session_status"] == "finished":
                finished_at = finished_at or clock
                if clock - finished_at > timedelta(minutes=2):
                    break
            await _sleep(REPLAY_TICK_SECONDS)
            clock += timedelta(seconds=REPLAY_TICK_SECONDS * relay.replay_speed)
        relay.status = "finished"

    async def _live(self, relay: Relay, feed: SessionFeed, session: Dict[str, Any]) -> None:
        end = parse_time(session["date_end"])
        finished_at = None
        while True:
            now = datetime.now(timezone.utc)
            await feed.refresh()
            state = build_state(feed.data, session, relay.session, relay.race_id)
            await self._publish(state)
            relay.clock = now.isoformat()
            done = state["session_status"] == "finished" or (end is not None and now > end + timedelta(minutes=30))
            if done:
                finished_at = finished_at or now
                if now - finished_at > timedelta(seconds=FINISHED_LINGER_SECONDS):
                    break
            await _sleep(LIVE_POLL_SECONDS)
        relay.status = "finished"
        if self._on_finished:
            try:
                await self._on_finished(relay.year, relay.gp, relay.session)
            except Exception:
                logger.exception("post-session ingest for %s failed", relay.race_id)

    async def schedule_loop(self) -> None:
        """With credentials: start a live relay for every session that's on now."""
        if not self.live_available():
            return
        client = self._client_factory()
        try:
            while True:
                try:
                    now = datetime.now(timezone.utc)
                    sessions = await client.get("sessions", **{
                        "date_start<": (now + timedelta(minutes=10)).isoformat(),
                        "date_end>": (now - timedelta(minutes=30)).isoformat(),
                    })
                    meetings = {}
                    for s in sessions:
                        code = CODE_FOR_NAME.get(s.get("session_name"))
                        if not code or s.get("is_cancelled"):
                            continue
                        if s["meeting_key"] not in meetings:
                            found = await client.get("meetings", meeting_key=s["meeting_key"])
                            meetings[s["meeting_key"]] = found[0]["meeting_name"] if found else None
                        if meetings[s["meeting_key"]]:
                            self.start(int(s["year"]), meetings[s["meeting_key"]], code)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.warning("live schedule check failed: %s", exc)
                await asyncio.sleep(SCHEDULE_CHECK_SECONDS)
        finally:
            await client.close()
