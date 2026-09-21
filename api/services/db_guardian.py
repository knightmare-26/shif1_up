"""Keeps the Supabase-backed services connected, and wakes a paused project.

Why this exists: free-tier Supabase projects pause after a week idle, and free
Render web services sleep after 15 minutes. When someone opens the site, Render
boots the API, the API tries to connect to a database that is paused, and —
because that connection used to be made once at startup — everything stayed
broken until someone restarted the service by hand.

The guardian owns that connection for the life of the process:

* it connects in the background, so the API always comes up and can answer
  /health (and the frontend can say what's happening);
* if the connection fails and a Supabase access token is configured, it asks
  the Management API what state the project is in and restores it if paused,
  then reconnects on its own once the project is back;
* while connected it checks the connection periodically (which also counts as
  activity for Supabase's inactivity timer) and reconnects if it drops.

It never logs credentials. Without SUPABASE_ACCESS_TOKEN it can't restore a
project — it just keeps retrying and reports the database as unavailable.
"""

import asyncio
import logging
import re
import time
from typing import Awaitable, Callable, Optional
from urllib.parse import urlsplit

import httpx

logger = logging.getLogger(__name__)

DEFAULT_API_URL = "https://api.supabase.com"

# Management API project statuses that mean "on its way up (or asleep)".
WAKING_STATUSES = {"INACTIVE", "COMING_UP", "RESTORING", "RESTARTING", "UPGRADING"}

READY = "ready"
CONNECTING = "connecting"
WAKING = "waking"
UNAVAILABLE = "unavailable"

MESSAGES = {
    READY: "",
    CONNECTING: "Connecting to the database…",
    WAKING: "The database is waking up after a period of inactivity. This usually takes 1–2 minutes.",
    UNAVAILABLE: "The database can't be reached right now. Retrying…",
}


def project_ref_from_url(database_url: str) -> Optional[str]:
    """The Supabase project ref, parsed from a pooler or direct connection URL."""
    try:
        url = urlsplit(database_url or "")
    except ValueError:
        return None
    if url.username and url.username.startswith("postgres."):  # pooler login: postgres.<ref>
        return url.username.split(".", 1)[1] or None
    host = url.hostname or ""
    if host.startswith("db.") and host.endswith(".supabase.co"):  # direct: db.<ref>.supabase.co
        return host[len("db."):-len(".supabase.co")] or None
    return None


def looks_paused(exc: BaseException) -> bool:
    """The pooler's signature for a paused (or missing) project."""
    return bool(re.search(r"tenant/user .* not found|ENOTFOUND", str(exc)))


class DatabaseGuardian:
    def __init__(
        self,
        connect: Callable[[], Awaitable[None]],
        disconnect: Callable[[], Awaitable[None]],
        ping: Callable[[], Awaitable[bool]],
        *,
        database_url: str = "",
        access_token: Optional[str] = None,
        project_ref: Optional[str] = None,
        api_url: str = DEFAULT_API_URL,
        retry_seconds: float = 15.0,
        keepalive_seconds: float = 300.0,
        connect_timeout: float = 25.0,
        min_attempt_gap: float = 5.0,
        restore_cooldown: float = 600.0,
        recently_restored_window: float = 300.0,
        transport: Optional[httpx.AsyncBaseTransport] = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._connect = connect
        self._disconnect = disconnect
        self._ping = ping
        self.access_token = access_token or None
        self.project_ref = project_ref or project_ref_from_url(database_url)
        self.api_url = api_url.rstrip("/")
        self.retry_seconds = retry_seconds
        self.keepalive_seconds = keepalive_seconds
        self.connect_timeout = connect_timeout
        self.min_attempt_gap = min_attempt_gap
        self.restore_cooldown = restore_cooldown
        self.recently_restored_window = recently_restored_window
        self._transport = transport
        self._clock = clock

        self.state = CONNECTING
        self.detail = ""
        self._last_attempt: Optional[float] = None
        self._last_restore: Optional[float] = None
        self._warned: set = set()
        self._nudge = asyncio.Event()
        self._task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------ status

    @property
    def ready(self) -> bool:
        return self.state == READY

    @property
    def can_restore(self) -> bool:
        return bool(self.access_token and self.project_ref)

    def snapshot(self) -> dict:
        """Safe to expose publicly: no project ref, no credentials, no error text."""
        return {
            "status": "ok" if self.ready else self.state,
            "state": self.state,
            "message": MESSAGES[self.state],
        }

    def _set(self, state: str, detail: str = "") -> None:
        if state != self.state:
            logger.info("database: %s -> %s%s", self.state, state, f" ({detail})" if detail else "")
        self.state, self.detail = state, detail

    def _warn_once(self, key: str, message: str, *args) -> None:
        if key not in self._warned:
            self._warned.add(key)
            logger.warning(message, *args)

    # --------------------------------------------------------------- lifecycle

    async def start(self) -> None:
        """Make the first connection attempt (bounded), then keep watching in the background."""
        await self.attempt()
        self._task = asyncio.create_task(self._run(), name="database-guardian")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def nudge(self) -> None:
        """Someone is waiting on the database — retry now instead of at the next interval."""
        if not self.ready:
            self._nudge.set()

    async def _sleep(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self._nudge.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass
        self._nudge.clear()

    async def _run(self) -> None:
        while True:
            try:
                if self.ready:
                    await self._sleep(self.keepalive_seconds)
                    await self.check_alive()
                else:
                    await self._sleep(self.retry_seconds)
                    await self.attempt()
            except asyncio.CancelledError:
                raise
            except Exception:  # the loop must never die
                logger.exception("database guardian loop error")
                await asyncio.sleep(self.retry_seconds)

    # ----------------------------------------------------------------- actions

    async def check_alive(self) -> bool:
        """Ping the live connection; drop it and start reconnecting if it's gone."""
        try:
            alive = await self._ping()
        except Exception:
            alive = False
        if not alive:
            logger.warning("database connection lost — reconnecting")
            try:
                await self._disconnect()
            except Exception:
                logger.exception("error closing lost database connection")
            self._set(CONNECTING)
        return alive

    async def attempt(self) -> None:
        """Try to connect; if that fails, work out why and wake the project if it's paused."""
        now = self._clock()
        if self._last_attempt is not None and now - self._last_attempt < self.min_attempt_gap:
            return
        self._last_attempt = now
        try:
            await asyncio.wait_for(self._connect(), timeout=self.connect_timeout)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self._diagnose(exc)
            return
        self._set(READY)
        self._last_restore = None
        logger.info("database connected")

    # --------------------------------------------------------------- diagnosis

    async def _diagnose(self, error: Exception) -> None:
        paused_hint = looks_paused(error)
        if not self.can_restore:
            self._set(UNAVAILABLE, type(error).__name__)
            self._warn_once(
                "no-token",
                "database unreachable (%s)%s. Set SUPABASE_ACCESS_TOKEN to let the API restore a "
                "paused project itself; until then restore it from the Supabase dashboard.",
                type(error).__name__,
                " — the pooler reports the project as paused" if paused_hint else "",
            )
            return

        status, http_status = await self._project_status()
        now = self._clock()

        if http_status in (401, 403):
            self._set(UNAVAILABLE, f"Supabase access token rejected (HTTP {http_status})")
            self._warn_once("token", "Supabase access token was rejected (HTTP %s)", http_status)
        elif status == "INACTIVE":
            if self._last_restore is None or now - self._last_restore >= self.restore_cooldown:
                self._last_restore = now
                code = await self._request_restore()
                logger.warning("database project is paused — restore requested (HTTP %s)", code)
            self._set(WAKING, "project paused")
        elif status in WAKING_STATUSES:
            self._set(WAKING, status)
        elif status is None:
            self._set(UNAVAILABLE, "Supabase Management API unreachable")
        elif self._last_restore is not None and now - self._last_restore < self.recently_restored_window:
            # Project reports active but the pooler needs a few more seconds after a restore.
            self._set(WAKING, "restore finishing")
        else:
            self._set(UNAVAILABLE, f"project {status}; connection failed ({type(error).__name__})")

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=15.0,
            transport=self._transport,
            headers={"Authorization": f"Bearer {self.access_token}"},
        )

    async def _project_status(self) -> "tuple[Optional[str], int]":
        try:
            async with self._client() as client:
                r = await client.get(f"{self.api_url}/v1/projects/{self.project_ref}")
            if r.status_code != 200:
                return None, r.status_code
            return r.json().get("status"), 200
        except (httpx.HTTPError, ValueError):
            return None, 0

    async def _request_restore(self) -> int:
        try:
            async with self._client() as client:
                r = await client.post(f"{self.api_url}/v1/projects/{self.project_ref}/restore")
            return r.status_code
        except httpx.HTTPError:
            return 0
