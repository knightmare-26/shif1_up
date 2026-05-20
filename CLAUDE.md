# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Run everything (recommended for development)
```bash
npm run dev          # Starts both backend + frontend concurrently
```

### Backend only
```bash
python start_backend.py          # Preferred: checks deps, sets env, starts uvicorn
# or directly:
uvicorn api.main:app --reload --port 8000
```
The API is served at `http://localhost:8000`, docs at `http://localhost:8000/docs`.

### Frontend only
```bash
npm start            # React dev server on http://localhost:3000
npm run build        # Production build
```

### Tests
```bash
pytest tests/                    # All tests
pytest tests/test_api.py -v      # Single file, verbose
pytest tests/ --cov=api          # With coverage
```

### Data ingestion
```bash
# Fast ingest (race results + standings, no telemetry — runs in minutes)
python ingest/simple_ingest.py --years 2024
python ingest/simple_ingest.py --years 2023 2024

# Full ingest with telemetry/Parquet (takes hours, large download)
python ingest/historical_ingest.py --years 2024
python ingest/incremental_ingest.py --years 2024
```

### Live poller (separate process)
```bash
RACE_YEAR=2024 RACE_GP=Bahrain python live/poller.py
```

### Docker
```bash
docker-compose up --build        # All services: api, redis, poller, worker
```

## Architecture

This is a full-stack F1 analytics platform with:
- **React frontend** (`src/`) — TypeScript, TailwindCSS, React Router, Chart.js
- **FastAPI backend** (`api/`) — Python, async, WebSocket support
- **DuckDB** — historical race/lap/telemetry storage (file: `data/f1_history.duckdb`)
- **Redis** — live race state + pub/sub for WebSocket fan-out
- **FastF1 + Ergast API** — external F1 data sources

### Backend service layer (`api/services/`)

| Service | Purpose |
|---|---|
| `simple_duckdb_service.py` | DuckDB historical storage with in-memory fallback |
| `redis_service.py` | Real Redis client for live state and pub/sub |
| `mock_redis_service.py` | In-memory Redis mock (used when Redis is unreachable) |
| `fastf1_service.py` | FastF1 library wrapper (years 2020–2023) |
| `ergast_service.py` | Ergast REST API wrapper (other years) |
| `cache_service.py` | In-process cache layer for API responses |

**Data source routing logic**: `api/main.py` uses `FASTF1_YEARS = [2020, 2021, 2022, 2023]` to decide whether to call FastF1 or Ergast for a given year.

**Redis fallback**: On startup, the API tries to connect to real Redis. If unavailable, it silently falls back to `MockRedisService` (in-memory dict). This means the app runs without Redis installed locally.

**DuckDB fallback**: Similarly, `SimpleDuckDBService` falls back to an in-memory dict if DuckDB is unavailable or the DB file doesn't exist yet. The API seeds sample data on every startup via `_load_sample_data()`.

### WebSocket live data flow

1. `live/poller.py` polls FastF1 for live session data and writes to Redis via `redis_service.set_live_state()` + `publish_update()`
2. `api/main.py:/ws/live/{race_id}` accepts WebSocket connections, sends initial state, then streams Redis pub/sub messages using `redis_service.subscribe_to_race()`
3. Frontend `LiveDataMonitor` / `LiveAnalytics` components connect to the WebSocket

### Frontend routing (`src/App.tsx`)

Auth state (from `AuthContext`) controls which routes are accessible. Unauthenticated users see public pages; authenticated users get the full dashboard with `Navigation` sidebar.

Frontend calls the backend via `src/services/backendApi.ts` (base URL from `REACT_APP_API_URL` env var, defaulting to `http://localhost:8000`). The backend exposes legacy `/api/*` endpoints specifically for this frontend client.

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `REDIS_URL` | `redis://localhost:6379` | Redis connection |
| `DUCKDB_PATH` | `data/f1_history.duckdb` | DuckDB file path |
| `FASTF1_CACHE_DIR` | `data/fastf1_cache` | FastF1 session cache |
| `CORS_ORIGINS` | `http://localhost:3000,...` | Allowed CORS origins |
| `RACE_YEAR` / `RACE_GP` | — | For `live/poller.py` |
| `REACT_APP_API_URL` | `http://localhost:8000` | Frontend API base URL |

### Key API endpoints

- `GET /health` — service health + Redis info
- `GET /drivers`, `GET /races` — historical data (DuckDB → FastF1/Ergast fallback)
- `GET /race/{race_id}/results`, `/race/{race_id}/laps` — race detail
- `GET /live/{race_id}/state` — current live state from Redis
- `WS /ws/live/{race_id}` — WebSocket live updates
- `GET /api/drivers`, `/api/constructors`, `/api/races` — legacy endpoints (frontend uses these)
- `POST /simulate/live/{race_id}` — inject mock live state for testing
