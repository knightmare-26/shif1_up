"""
Shif1 UP - FastAPI Backend
Features: DuckDB historical data, Upstash Redis live state, WebSocket streaming
"""

import asyncio
import json
import logging
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

import uvicorn
from dotenv import load_dotenv
load_dotenv()

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from services.simple_duckdb_service import SimpleDuckDBService
from services.supabase_f1_service import SupabaseF1Service
from services.postgres_service import PostgresService
from services.redis_service import RedisService
from services.mock_redis_service import MockRedisService
from services.fastf1_service import FastF1Service
from services.ergast_service import ErgastService
from services.cache_service import CacheService
from services.db_guardian import DatabaseGuardian
from services.redact import redact_url
from services.auth_service import (
    hash_password, verify_password, create_access_token, decode_token, new_user_id
)
from services import ingest_service
from services.prediction_service import PredictionService
from models.f1_models import (
    DriverStanding, ConstructorStanding, RaceEvent,
    SessionData, LapData, TelemetryData, WeatherData, RaceResult,
)

# ---------------------------------------------------------------------------
# Logging — structured JSON when LOG_FORMAT=json; configurable level via
# LOG_LEVEL (default INFO)
# ---------------------------------------------------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FORMAT = os.getenv("LOG_FORMAT", "text")  # "json" for production

if LOG_FORMAT == "json":
    from pythonjsonlogger.json import JsonFormatter
    _handler = logging.StreamHandler()
    _handler.setFormatter(JsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        rename_fields={"asctime": "timestamp", "levelname": "level"},
    ))
    logging.root.handlers = [_handler]
    logging.root.setLevel(LOG_LEVEL)
else:
    logging.basicConfig(level=LOG_LEVEL)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
DATABASE_URL = os.getenv("DATABASE_URL", "")
DUCKDB_PATH = os.getenv("DUCKDB_PATH", "data/f1_history.duckdb")
FASTF1_CACHE_DIR = os.getenv("FASTF1_CACHE_DIR", "data/fastf1_cache")
# Comma-separated list of allowed CORS origins
CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
).split(",")

# Years where FastF1 has complete session data
FASTF1_YEARS = [2020, 2021, 2022, 2023, 2024]

# Shared secret for service-to-service calls (e.g. live/poller.py -> /admin/ingest/race)
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "")

# ---------------------------------------------------------------------------
# Global service instances
# ---------------------------------------------------------------------------
redis_service = None
duckdb_service = None
postgres_service = None
fastf1_service = None
ergast_service = None
cache_service = None
database_guardian: Optional[DatabaseGuardian] = None
MODEL_DIR = os.getenv("MODEL_DIR", "data/models")
prediction_service = PredictionService(model_dir=MODEL_DIR)


async def _init_redis() -> Any:
    """Try real Redis first; fall back to mock if unavailable."""
    try:
        svc = RedisService(REDIS_URL)
        await svc.initialize()
        logger.info("✅ Redis connected (%s)", redact_url(REDIS_URL))
        return svc
    except Exception as exc:
        logger.warning("⚠️  Redis unavailable (%s) — using in-memory mock", exc)
        svc = MockRedisService(REDIS_URL)
        await svc.initialize()
        return svc


# ---------------------------------------------------------------------------
# Supabase connection lifecycle (owned by DatabaseGuardian — see db_guardian.py)
# ---------------------------------------------------------------------------
async def _connect_database() -> None:
    """Open the Supabase pools for auth and F1 data. Raises if either can't
    connect, leaving nothing half-open (also on cancellation, e.g. a timeout)."""
    global duckdb_service, postgres_service
    users = PostgresService(DATABASE_URL)
    f1 = SupabaseF1Service(DATABASE_URL)
    try:
        await users.initialize()
        await f1.initialize()
    except BaseException:
        for svc in (f1, users):
            try:
                await svc.cleanup()
            except Exception:
                pass
        raise
    postgres_service, duckdb_service = users, f1
    logger.info("✅ Using Supabase for auth and F1 historical data")


async def _disconnect_database() -> None:
    global duckdb_service, postgres_service
    old = (duckdb_service, postgres_service)
    duckdb_service = postgres_service = None
    for svc in old:
        if svc:
            try:
                await svc.cleanup()
            except Exception:
                logger.exception("error closing database pool")


async def _ping_database() -> bool:
    pool = getattr(duckdb_service, "pool", None)
    if pool is None:
        return False
    try:
        async with pool.acquire(timeout=10) as conn:
            return await conn.fetchval("SELECT 1", timeout=10) == 1
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_service, duckdb_service, fastf1_service, ergast_service, cache_service, database_guardian

    logger.info("🚀 Starting Shif1 UP API...")

    redis_service = await _init_redis()

    if DATABASE_URL:
        # The API must come up even if the database is paused, so it can answer
        # /health and tell the frontend what's going on. The guardian makes the
        # first attempt now (bounded), then keeps retrying — and wakes a paused
        # Supabase project if SUPABASE_ACCESS_TOKEN is set.
        database_guardian = DatabaseGuardian(
            connect=_connect_database,
            disconnect=_disconnect_database,
            ping=_ping_database,
            database_url=DATABASE_URL,
            access_token=os.getenv("SUPABASE_ACCESS_TOKEN"),
            project_ref=os.getenv("SUPABASE_PROJECT_REF"),
            api_url=os.getenv("SUPABASE_API_URL", "https://api.supabase.com"),
        )
        await database_guardian.start()
    else:
        logger.info("ℹ️  No DATABASE_URL — using local DuckDB, auth endpoints disabled")
        duckdb_service = SimpleDuckDBService(DUCKDB_PATH)
        await duckdb_service.initialize()

    fastf1_service = FastF1Service()
    ergast_service = ErgastService()
    cache_service = CacheService()
    await cache_service.initialize()

    if not DATABASE_URL:
        await _load_sample_data()

    # Load pre-trained ML models from disk (avoids cold retrain on every restart)
    if prediction_service.load_from_disk():
        logger.info("✅ Prediction models loaded from disk")
    else:
        logger.info("ℹ️  No saved models found — will train on first /predict request")

    logger.info("✅ All services ready")
    yield

    logger.info("🛑 Shutting down...")
    if database_guardian:
        await database_guardian.stop()
    if redis_service:
        await redis_service.cleanup()
    if postgres_service:
        await postgres_service.cleanup()
    if duckdb_service:
        await duckdb_service.cleanup()
    if cache_service:
        await cache_service.cleanup()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Shif1 UP API",
    description="F1 Analytics Platform — DuckDB · Redis · WebSocket",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

RATE_LIMIT = os.getenv("RATE_LIMIT", "60/minute")
RATE_LIMIT_AUTH = os.getenv("RATE_LIMIT_AUTH", "10/minute")

limiter = Limiter(key_func=get_remote_address, default_limits=[RATE_LIMIT])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Endpoints that read from the Supabase database. While the guardian is
# (re)connecting they answer 503 "database_waking" — quickly, and with a message
# the frontend can show — instead of failing with an opaque 500.
DB_BACKED_PREFIXES = (
    "/race/", "/admin/", "/auth/",
    "/predict/qualifying", "/predict/race", "/predict/sprint", "/predict/backtest", "/predict/train",
)


async def _database_gate(request: Request, call_next):
    guardian = database_guardian
    if guardian and not guardian.ready and request.url.path.startswith(DB_BACKED_PREFIXES):
        guardian.nudge()
        snapshot = guardian.snapshot()
        return JSONResponse(
            status_code=503,
            content={"detail": "database_waking", **snapshot},
            headers={"Retry-After": "15"},
        )
    return await call_next(request)


# Registered before CORSMiddleware on purpose: middleware added later wraps
# earlier ones, so CORS headers end up on the 503s too (otherwise the browser
# reports an opaque network error instead of a readable response).
app.add_middleware(BaseHTTPMiddleware, dispatch=_database_gate)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Sample data loader (used until real ingestion runs)
# ---------------------------------------------------------------------------
async def _load_sample_data():
    if getattr(duckdb_service, "backend", None) == "postgres":
        return  # Supabase is populated via ingest, not sample data
    try:
        await duckdb_service.store_drivers([
            {"driver_id": "verstappen", "full_name": "Max Verstappen",   "nationality": "Dutch",       "number": 1},
            {"driver_id": "norris",     "full_name": "Lando Norris",     "nationality": "British",     "number": 4},
            {"driver_id": "leclerc",    "full_name": "Charles Leclerc",  "nationality": "Monegasque",  "number": 16},
            {"driver_id": "piastri",    "full_name": "Oscar Piastri",    "nationality": "Australian",  "number": 81},
            {"driver_id": "sainz",      "full_name": "Carlos Sainz",     "nationality": "Spanish",     "number": 55},
        ])
        await duckdb_service.store_constructors([
            {"constructor_id": "red_bull", "constructor_name": "Red Bull Racing Honda RBPT", "nationality": "Austrian"},
            {"constructor_id": "mclaren",  "constructor_name": "McLaren Mercedes",           "nationality": "British"},
            {"constructor_id": "ferrari",  "constructor_name": "Ferrari",                    "nationality": "Italian"},
        ])
        await duckdb_service.store_races([
            {"race_id": "2024_Bahrain",      "year": 2024, "round": 1, "gp": "Bahrain",      "date": "2024-03-02", "circuit_name": "Bahrain International Circuit", "country": "Bahrain"},
            {"race_id": "2024_Saudi_Arabia", "year": 2024, "round": 2, "gp": "Saudi Arabia", "date": "2024-03-09", "circuit_name": "Jeddah Corniche Circuit",       "country": "Saudi Arabia"},
        ])
        await duckdb_service.store_race_results("2024_Bahrain", [
            {"position": 1, "driver_id": "verstappen", "constructor_id": "red_bull", "points": 25, "time": "1:31:44.742", "fastest_lap": True,  "fastest_lap_time": "1:33.660", "status": "Finished"},
            {"position": 2, "driver_id": "norris",     "constructor_id": "mclaren",  "points": 18, "time": "+22.457",     "fastest_lap": False, "fastest_lap_time": None,        "status": "Finished"},
        ])
        logger.info("✅ Sample data loaded")
    except Exception as exc:
        logger.error("❌ Failed to load sample data: %s", exc)


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

_bearer = HTTPBearer()


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(_bearer)):
    payload = decode_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = await postgres_service.get_user_by_id(payload.get("sub", ""))
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


async def require_admin_or_internal(
    x_internal_key: Optional[str] = Header(None, alias="X-Internal-Key"),
    authorization: Optional[str] = Header(None),
):
    """Allow either the internal service key (live/poller.py) or an admin JWT."""
    if INTERNAL_API_KEY and x_internal_key == INTERNAL_API_KEY:
        return {"internal": True}
    if authorization and authorization.lower().startswith("bearer "):
        payload = decode_token(authorization.split(" ", 1)[1])
        if payload:
            user = await postgres_service.get_user_by_id(payload.get("sub", ""))
            if user and user.get("is_admin"):
                return user
    raise HTTPException(status_code=403, detail="Admin access required")


# ---------------------------------------------------------------------------
# Auth request/response models
# ---------------------------------------------------------------------------

class SignupRequest(BaseModel):
    username: str
    email: str
    password: str
    preferences: dict = {}


class LoginRequest(BaseModel):
    username: str
    password: str


# ===========================================================================
# AUTH
# ===========================================================================

@app.post("/auth/signup")
@limiter.limit(RATE_LIMIT_AUTH)
async def auth_signup(request: Request, body: SignupRequest):
    if len(body.username) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters")
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    user_data = {
        "id": new_user_id(),
        "username": body.username,
        "email": body.email,
        "hashed_password": hash_password(body.password),
        "preferences": body.preferences,
    }
    success = await postgres_service.create_user(user_data)
    if not success:
        raise HTTPException(status_code=409, detail="Username or email already exists")

    token = create_access_token({"sub": user_data["id"]})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user_data["id"],
            "username": user_data["username"],
            "email": user_data["email"],
            "preferences": user_data["preferences"],
            "is_admin": False,
        },
    }


@app.post("/auth/login")
@limiter.limit(RATE_LIMIT_AUTH)
async def auth_login(request: Request, body: LoginRequest):
    user = await postgres_service.get_user_by_username(body.username)
    if not user or not verify_password(body.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = create_access_token({"sub": user["id"]})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "username": user["username"],
            "email": user["email"],
            "preferences": user.get("preferences", {}),
            "is_admin": user.get("is_admin", False),
        },
    }


@app.get("/auth/me")
async def auth_me(user=Depends(get_current_user)):
    return {
        "id": user["id"],
        "username": user["username"],
        "email": user["email"],
        "preferences": user.get("preferences", {}),
        "is_admin": user.get("is_admin", False),
    }


@app.patch("/auth/me/preferences")
async def auth_update_preferences(preferences: dict, user=Depends(get_current_user)):
    await postgres_service.update_user_preferences(user["id"], preferences)
    return {"message": "Preferences updated"}


# ===========================================================================
# HEALTH
# ===========================================================================

async def _probe_redis() -> Dict[str, Any]:
    """Report Redis connectivity. Never raises — always returns a status dict."""
    if redis_service is None:
        return {"status": "unavailable", "kind": "none"}
    kind = "mock" if isinstance(redis_service, MockRedisService) else "real"
    try:
        info = await redis_service.get_redis_info()
        return {"status": "ok", "kind": kind, "info": info}
    except Exception as exc:
        logger.warning("health: redis probe failed: %s", exc)
        return {"status": "error", "kind": kind, "error": str(exc)}


async def _probe_duckdb() -> Dict[str, Any]:
    """Report DuckDB connectivity via a trivial probe query. Never raises."""
    if duckdb_service is None:
        return {"status": "unavailable"}
    try:
        rows = await duckdb_service._run_query("SELECT 1 AS probe")
        ok = bool(rows) and rows[0].get("probe") == 1
        return {"status": "ok" if ok else "degraded", "path": DUCKDB_PATH}
    except Exception as exc:
        logger.warning("health: duckdb probe failed: %s", exc)
        return {"status": "error", "error": str(exc)}


@app.get("/health")
async def health_check():
    guardian = database_guardian
    if guardian:
        # A visit while the database is down is a reason to retry right now, and
        # (when connected) the probe below is activity for Supabase's idle timer.
        guardian.nudge()
    redis_check = await _probe_redis()
    duckdb_check = await _probe_duckdb()

    # DuckDB is critical — any non-ok status degrades the overall report.
    # Redis falls back to mock gracefully, so a real-Redis failure is only
    # "degraded" (the app still works).
    if duckdb_check["status"] == "error":
        overall = "error"
    elif duckdb_check["status"] != "ok" or redis_check["status"] != "ok":
        overall = "degraded"
    else:
        overall = "ok"

    body = {
        "status": overall,
        "timestamp": datetime.utcnow().isoformat(),
        "service": "Shif1 UP API",
        "version": "2.0.0",
        "checks": {
            "redis": redis_check,
            "duckdb": duckdb_check,
        },
    }
    if guardian:
        # Present only when running against Supabase. `state` drives the frontend's
        # "waking up" banner; `self_healing` tells supervisors not to restart us.
        body["checks"]["database"] = {**guardian.snapshot(), "self_healing": True}
    if overall == "error":
        raise HTTPException(status_code=503, detail=body)
    return body


# ===========================================================================
# DRIVERS
# ===========================================================================

@app.get("/drivers")
async def get_drivers(year: Optional[int] = None):
    try:
        if year:
            drivers = await duckdb_service.get_drivers_by_year(year)
            if not drivers:
                if year in FASTF1_YEARS:
                    drivers = await fastf1_service.get_driver_standings(year)
                else:
                    async with ergast_service as ergast:
                        drivers = await ergast.get_driver_standings(year)
        else:
            drivers = await duckdb_service.get_all_drivers()
        return drivers
    except Exception as exc:
        logger.error("❌ get_drivers: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/drivers/{driver_id}")
async def get_driver_details(driver_id: str, year: Optional[int] = None):
    try:
        year = year or datetime.now().year
        data = await duckdb_service.get_driver_details(driver_id, year)
        if not data:
            data = await fastf1_service.get_driver_details(driver_id, year)
        return data
    except Exception as exc:
        logger.error("❌ get_driver_details: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


# ===========================================================================
# RACES
# ===========================================================================

@app.get("/races")
async def get_races(year: Optional[int] = None):
    try:
        year = year or datetime.now().year
        races = await duckdb_service.get_races_by_year(year)
        if not races:
            if year in FASTF1_YEARS:
                races = await fastf1_service.get_race_schedule(year)
            else:
                async with ergast_service as ergast:
                    races = await ergast.get_race_schedule(year)
        return races
    except Exception as exc:
        logger.error("❌ get_races: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


def _parse_race_id(race_id: str) -> tuple:
    parts = race_id.split("_", 1)
    if len(parts) != 2 or not parts[0].isdigit():
        raise HTTPException(status_code=400, detail="Invalid race_id format — expected '<year>_<grand_prix>'")
    return int(parts[0]), parts[1]


# Approximate official team colors (hex, no '#'), keyed by constructor_id.
TEAM_COLORS = {
    "red_bull": "3671C6",
    "ferrari": "E8002D",
    "mercedes": "00D2BE",
    "mclaren": "FF8000",
    "aston_martin": "229971",
    "alpine": "2293D1",
    "williams": "64C4FF",
    "haas": "B6BABD",
    "rb": "6692FF",
    "sauber": "52E252",
    "alphatauri": "2B4562",
    "alfa": "981E32",
}

# driver_id -> headshot URL (empty when unknown; frontend hides broken images)
DRIVER_HEADSHOTS: Dict[str, str] = {}

_TIMEDELTA_RE = re.compile(r"(?:(\d+)\s+days?,?\s*)?(\d+):(\d+):(\d+(?:\.\d+)?)")


def _parse_timedelta_seconds(value: str) -> float:
    """Best-effort parse of a pandas Timedelta repr (e.g. '0 days 01:31:44.742000') into seconds."""
    if not value:
        return 0.0
    match = _TIMEDELTA_RE.search(value)
    if not match:
        return 0.0
    days, hours, minutes, seconds = match.groups()
    total = float(seconds) + int(minutes) * 60 + int(hours) * 3600
    if days:
        total += int(days) * 86400
    return total


def _normalize_db_results(rows: List[Dict]) -> List[Dict]:
    """DB rows are a reduced snake_case shape; the frontend table expects the
    same PascalCase fields FastF1's session.results DataFrame provides. This
    conforms DB-sourced rows to that shape so both data sources render the
    same way."""
    normalized = []
    for row in rows:
        driver_id = row.get("driver_id") or ""
        full_name = row.get("driver_name") or ""
        first_name, _, last_name = full_name.partition(" ")
        status = row.get("status") or ""
        position = row.get("position")
        grid = row.get("grid")
        unclassified_terms = ("retired", "did not finish", "disqualified", "did not start", "withdrawn")
        is_unclassified = any(term in status.lower() for term in unclassified_terms)
        normalized.append({
            "DriverNumber": str(row.get("driver_number") or ""),
            "BroadcastName": "",
            "Abbreviation": driver_id.upper(),
            "DriverId": driver_id,
            "TeamName": row.get("constructor_name") or "",
            "TeamColor": TEAM_COLORS.get(row.get("constructor_id") or "", "666666"),
            "TeamId": row.get("constructor_id") or "",
            "FirstName": first_name,
            "LastName": last_name,
            "FullName": full_name,
            "HeadshotUrl": DRIVER_HEADSHOTS.get(driver_id, ""),
            "CountryCode": row.get("country_code") or "",
            "Position": str(position) if position is not None else "",
            "ClassifiedPosition": str(position) if "finish" in status.lower() else (status[:3].upper() or "NC"),
            "GridPosition": str(grid) if grid is not None else "",
            "Time": _parse_timedelta_seconds(row.get("time") or ""),
            "Status": status,
            "Points": str(row.get("points", "")),
            "Laps": str(row.get("laps_completed")) if row.get("laps_completed") is not None else "",
        })
    return normalized


@app.get("/race/{race_id}/results")
async def get_race_results(race_id: str, session: str = "R"):
    """`session` is one of R/S/Q/SQ/FP1/FP2/FP3. Tries the DB first; on a
    miss, fetches that session from FastF1 and writes it through to the DB
    (via the same path admin ingest uses) so the next request for it is
    fast — avoids either a slow live fetch on every call or a huge upfront
    backfill for every session type across every season."""
    session_type = ingest_service.SESSION_TYPE_MAP.get(session, "race")
    try:
        results = await duckdb_service.get_race_results(race_id, session_type=session_type)
        if not results:
            year, gp = _parse_race_id(race_id)
            try:
                ingested = await ingest_service.ingest_single_race(
                    duckdb_service, year, gp, include_laps=False, session=session
                )
            except Exception as exc:
                # Most commonly: this weekend has no such session (e.g. Sprint
                # requested for a non-sprint round) — not a server error.
                logger.info("No %s session for %s: %s", session_type, race_id, exc)
                ingested = {"stored": False}
            if ingested.get("stored"):
                results = await duckdb_service.get_race_results(race_id, session_type=session_type)
        if results:
            return _normalize_db_results(results)
        raise HTTPException(status_code=404, detail=f"No {session_type} results found for {race_id}")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("❌ get_race_results: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/race/{race_id}/laps")
async def get_race_laps(race_id: str, driver: Optional[str] = None):
    try:
        laps = await duckdb_service.get_race_laps(race_id, driver)
        if not laps:
            year, gp = _parse_race_id(race_id)
            laps = await fastf1_service.get_session_laps(year, gp, "R", driver)
        return laps
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("❌ get_race_laps: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


# ===========================================================================
# LIVE DATA
# ===========================================================================

def _unwrap_live_state(envelope: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Flatten a Redis state/update envelope to the shape the frontend expects.

    Redis stores `{race_id, timestamp, state: {...}}` from set_live_state, and
    publishes `{race_id, timestamp, update: {type, state: {...}}}` from
    publish_update. The frontend LiveState is the inner `state` dict.
    """
    if not envelope:
        return None
    if "state" in envelope and isinstance(envelope["state"], dict):
        return envelope["state"]
    update = envelope.get("update")
    if isinstance(update, dict) and isinstance(update.get("state"), dict):
        return update["state"]
    return envelope


@app.get("/live/{race_id}/state")
async def get_live_state(race_id: str):
    try:
        envelope = await redis_service.get_live_state(race_id)
        state = _unwrap_live_state(envelope)
        if not state:
            state = {
                "race_id": race_id,
                "session_status": "no_data",
                "message": "No live data available — poller not running",
                "timestamp": datetime.utcnow().isoformat(),
            }
        return state
    except Exception as exc:
        logger.error("❌ get_live_state: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.websocket("/ws/live/{race_id}")
async def websocket_live_updates(websocket: WebSocket, race_id: str):
    await websocket.accept()
    try:
        initial_envelope = await redis_service.get_live_state(race_id)
        initial_state = _unwrap_live_state(initial_envelope)
        if initial_state:
            await websocket.send_text(json.dumps({"type": "initial_state", "data": initial_state}))

        async for message in redis_service.subscribe_to_race(race_id):
            flat = _unwrap_live_state(message)
            if flat is None:
                continue
            try:
                await websocket.send_text(json.dumps({"type": "update", "data": flat}))
            except WebSocketDisconnect:
                break
            except Exception as exc:
                logger.error("❌ WS send error: %s", exc)
                break
    except WebSocketDisconnect:
        logger.info("WS disconnected for race %s", race_id)
    except Exception as exc:
        logger.error("❌ WS error for race %s: %s", race_id, exc)
    finally:
        logger.info("WS closed for race %s", race_id)


# ===========================================================================
# LEGACY /api/* ENDPOINTS  (frontend backendApi.ts uses these)
# ===========================================================================

@app.get("/api/drivers", response_model=List[DriverStanding])
async def legacy_driver_standings(year: int = None, round: int = None, use_cache: bool = True):
    try:
        year = year or datetime.now().year
        cache_key = f"driver_standings_{year}_{round or 'current'}"
        if use_cache:
            cached = await cache_service.get(cache_key)
            if cached:
                return cached
        if year in FASTF1_YEARS:
            standings = await fastf1_service.get_driver_standings(year, round)
        else:
            async with ergast_service as ergast:
                standings = await ergast.get_driver_standings(year, round)
        await cache_service.set(cache_key, standings, ttl=3600)
        return standings
    except Exception as exc:
        logger.error("❌ legacy_driver_standings: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/constructors", response_model=List[ConstructorStanding])
async def legacy_constructor_standings(year: int = None, round: int = None, use_cache: bool = True):
    try:
        year = year or datetime.now().year
        cache_key = f"constructor_standings_{year}_{round or 'current'}"
        if use_cache:
            cached = await cache_service.get(cache_key)
            if cached:
                return cached
        if year in FASTF1_YEARS:
            standings = await fastf1_service.get_constructor_standings(year, round)
        else:
            async with ergast_service as ergast:
                standings = await ergast.get_constructor_standings(year, round)
        await cache_service.set(cache_key, standings, ttl=3600)
        return standings
    except Exception as exc:
        logger.error("❌ legacy_constructor_standings: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/races", response_model=List[RaceEvent])
async def legacy_race_schedule(year: int = None, use_cache: bool = True):
    """Always sourced from FastF1 (not the FASTF1_YEARS-gated routing used
    for standings) — confirmed reliable across 2000-2026. Ergast's
    circuit_name ("Circuit de Monaco") and FastF1's ("Monaco") don't match,
    and circuit_name from this endpoint feeds lookups elsewhere (track
    info, predictions) that are keyed to FastF1's convention — mixing
    sources per-year silently broke those for any year outside 2020-2024."""
    try:
        year = year or datetime.now().year
        cache_key = f"race_schedule_{year}"
        if use_cache:
            cached = await cache_service.get(cache_key)
            if cached:
                return cached
        schedule = await fastf1_service.get_race_schedule(year)
        await cache_service.set(cache_key, schedule, ttl=7200)
        return schedule
    except Exception as exc:
        logger.error("❌ legacy_race_schedule: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


# ===========================================================================
# CACHE MANAGEMENT
# ===========================================================================

@app.post("/api/cache/clear")
async def clear_cache(user=Depends(get_current_user)):
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    try:
        await cache_service.clear_all()
        return {"message": "Cache cleared"}
    except Exception as exc:
        logger.error("❌ clear_cache: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/cache/stats")
async def cache_stats():
    try:
        return await cache_service.get_stats()
    except Exception as exc:
        logger.error("❌ cache_stats: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


# ===========================================================================
# ADMIN — INGEST
# ===========================================================================

class IngestRequest(BaseModel):
    years: List[int] = [2024]
    laps: bool = False


async def _run_ingest_and_retrain(years: List[int], laps: bool):
    await ingest_service.run_ingest(duckdb_service, years, laps)
    if not ingest_service.status.get("error"):
        result = await prediction_service.train(duckdb_service)
        logger.info("Post-ingest retrain (years=%s): %s", years, result)


@app.post("/admin/ingest")
async def start_ingest(body: IngestRequest, background_tasks: BackgroundTasks, user=Depends(get_current_user)):
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    if ingest_service.status["running"]:
        raise HTTPException(status_code=409, detail="Ingest already running")
    background_tasks.add_task(_run_ingest_and_retrain, body.years, body.laps)
    return {"message": f"Ingest started for years {body.years}", "laps": body.laps}


class IngestRaceRequest(BaseModel):
    year: int
    event: str  # GP name (e.g. "Bahrain") or round number as a string
    laps: bool = False
    session: str = "R"  # "R" for the main race, "S" for a sprint race


async def _ingest_race_and_retrain(year: int, event, laps: bool, session: str):
    result = await ingest_service.ingest_single_race(duckdb_service, year, event, laps, session=session)
    if result.get("stored"):
        train_result = await prediction_service.train(duckdb_service)
        logger.info("Post-ingest retrain (%s, session=%s): %s", result.get("race_id"), session, train_result)


@app.post("/admin/ingest/race")
async def ingest_race(
    body: IngestRaceRequest,
    background_tasks: BackgroundTasks,
    _auth=Depends(require_admin_or_internal),
):
    """Ingest a single race or sprint session's results, then retrain the
    prediction models on the fresh data — used by an admin backfill or the
    live poller once it detects a session has ended."""
    event = int(body.event) if body.event.isdigit() else body.event
    background_tasks.add_task(_ingest_race_and_retrain, body.year, event, body.laps, body.session)
    return {"message": f"Ingest started for {body.year} {body.event} (session={body.session})"}


@app.get("/admin/ingest/status")
async def ingest_status(user=Depends(get_current_user)):
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return ingest_service.status


@app.get("/admin/db/stats")
async def db_stats(user=Depends(get_current_user)):
    """Row counts for each DuckDB table — used by the Data Manager UI."""
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    try:
        counts = {}
        for table in ("drivers", "constructors", "races", "race_results", "laps"):
            rows = await duckdb_service._run_query(f"SELECT COUNT(*) AS n FROM {table}")
            counts[table] = rows[0]["n"] if rows else 0
        years_rows = await duckdb_service._run_query(
            "SELECT DISTINCT year FROM races ORDER BY year"
        )
        counts["years"] = [r["year"] for r in years_rows]
        return counts
    except Exception as exc:
        logger.error("❌ db_stats: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


# ===========================================================================
# SIMULATE (dev / testing only)
# ===========================================================================

@app.post("/simulate/live/{race_id}")
@limiter.limit(RATE_LIMIT_AUTH)
async def simulate_live(request: Request, race_id: str):
    """Push mock live state into Redis for local testing."""
    try:
        state = {
            "race_id": race_id,
            "session_status": "live",
            "track_status": "green",
            "lap": 15,
            "total_laps": 57,
            "leader": "VER",
            "positions": [
                {"driver_id": "VER", "driver_name": "Max Verstappen",  "position": 1, "tyre": "SOFT", "gap": None,      "interval": None,      "last_lap_time": "1:33.660", "status": "Running"},
                {"driver_id": "NOR", "driver_name": "Lando Norris",    "position": 2, "tyre": "SOFT", "gap": "+22.457", "interval": "+22.457", "last_lap_time": "1:34.120", "status": "Running"},
                {"driver_id": "LEC", "driver_name": "Charles Leclerc", "position": 3, "tyre": "MEDIUM","gap": "+31.204", "interval": "+8.747",  "last_lap_time": "1:34.510", "status": "Running"},
            ],
            "timestamp": datetime.utcnow().isoformat(),
        }
        await redis_service.set_live_state(race_id, state)
        await redis_service.publish_update(race_id, {"type": "state_update", "state": state})
        return {"message": f"Simulation started for {race_id}"}
    except Exception as exc:
        logger.error("❌ simulate_live: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


# ===========================================================================
# PREDICTIONS
# ===========================================================================

@app.get("/predict/status")
async def predict_status():
    """Training status of the prediction models."""
    return prediction_service.training_status()


@app.get("/predict/circuits")
async def predict_circuits():
    """List races on the current season calendar that haven't happened yet —
    predicting an already-run race isn't useful, so past rounds are excluded."""
    if not prediction_service._trained:
        await prediction_service.train(duckdb_service)

    year = datetime.now().year
    try:
        # Always use FastF1's schedule here (not the FASTF1_YEARS-gated
        # routing used elsewhere) — its circuit_name convention (event
        # Location, e.g. "Zandvoort") is what ingest_service stores on
        # race_results, so predictions can match circuit-specific history.
        # Ergast's circuitName ("Circuit Park Zandvoort") wouldn't match.
        schedule = await fastf1_service.get_race_schedule(year)
    except Exception as exc:
        logger.error("❌ predict_circuits: failed to load %s schedule: %s", year, exc)
        return []

    today = datetime.utcnow().date().isoformat()
    upcoming = sorted((r for r in schedule if r.date >= today), key=lambda r: r.round)
    return [
        {
            "round": r.round, "race_name": r.race_name, "circuit_name": r.circuit_name,
            "date": r.date, "is_sprint": r.is_sprint,
        }
        for r in upcoming
    ]


@app.post("/predict/train")
async def predict_train(background_tasks: BackgroundTasks, user=Depends(get_current_user)):
    """(Re-)train prediction models on current DuckDB data."""
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    if prediction_service._trained:
        # Force retrain
        prediction_service._trained = False
    async def _do_train():
        result = await prediction_service.train(duckdb_service)
        logger.info("Prediction training result: %s", result)
    background_tasks.add_task(_do_train)
    return {"message": "Model training started in background. Check /predict/status for progress."}


@app.get("/predict/qualifying")
async def predict_qualifying(circuit: str):
    """Predict qualifying grid positions for all drivers at a given circuit."""
    try:
        result = await prediction_service.predict_qualifying(circuit, duckdb_service)
        if not result.get("success"):
            raise HTTPException(status_code=422, detail=result.get("error"))
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("predict_qualifying: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/predict/race")
async def predict_race(circuit: str):
    """Predict race finishing positions for all drivers at a given circuit."""
    try:
        result = await prediction_service.predict_race(circuit, duckdb_service)
        if not result.get("success"):
            raise HTTPException(status_code=422, detail=result.get("error"))
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("predict_race: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/predict/sprint")
async def predict_sprint(circuit: str):
    """Predict sprint race finishing positions for all drivers at a given circuit."""
    try:
        result = await prediction_service.predict_sprint(circuit, duckdb_service)
        if not result.get("success"):
            raise HTTPException(status_code=422, detail=result.get("error"))
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("predict_sprint: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/predict/backtest")
async def predict_backtest():
    """Score the current models against real results from the past 3 seasons —
    powers the Predictions page's Predicted vs Actual tab."""
    try:
        await prediction_service._ensure_trained(duckdb_service)
        return prediction_service.backtest(years_back=3)
    except Exception as exc:
        logger.error("predict_backtest: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
