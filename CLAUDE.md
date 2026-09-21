# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **Secrets**: actual service URLs, connection strings, and API keys live in `CLAUDE.local.md` (gitignored — never committed).

## Commands

### Run everything (recommended for development)
```bash
npm run dev          # Starts both backend + frontend concurrently
npm run up           # Same, but supervised: health-checks both and restarts whichever stops responding
```

`scripts/health_poller.py` (stdlib only; `--check` prints status and exits, `--only backend|frontend`). It adopts servers that are already healthy, writes child output to `logs/`, and restarts the backend when `/health` reports `degraded` (the DB connection is made once at startup, so a failure sticks until restart). If the Supabase project is paused it says so; set `SUPABASE_ACCESS_TOKEN` (Supabase dashboard → Account → Access Tokens, in `.env`) and it restores the project via the Management API, then restarts the backend. A running poller also keeps a free-tier project from re-pausing, since `/health` runs `SELECT 1`.

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
python ingest/simple_ingest.py --years 2022 2023 2024   # also populates grid column

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

Full-stack F1 analytics platform with:
- **React frontend** (`src/`) — TypeScript, TailwindCSS, React Router, Chart.js, Framer Motion
- **FastAPI backend** (`api/`) — Python, async, WebSocket support
- **DuckDB** — historical race/lap/telemetry storage (`data/f1_history.duckdb`; bundled in Docker image)
- **Supabase PostgreSQL** — users/auth table; F1 data migration approved (not yet done)
- **Upstash Redis** — live race WebSocket state + pub/sub fan-out
- **FastF1** — external F1 data source (years 2020–2024)
- **Jolpica-Ergast API** — external F1 data source for other years (ergast.com shut down 2024)

### Deployment (Render)

| Service | Type | Notes |
|---------|------|-------|
| `shif1-up-api` | Render Docker Web Service | `env: docker`; requirements at `api/requirements.txt` |
| `shif1-up-frontend` | Render Static Site | `public/_redirects` for SPA routing |

Config in `render.yaml`. Secrets (`REDIS_URL`, `DATABASE_URL`, `CORS_ORIGINS`, `REACT_APP_API_URL`) set in Render dashboard — never committed.

### Backend service layer (`api/services/`)

| Service | Purpose |
|---|---|
| `simple_duckdb_service.py` | DuckDB historical F1 storage (drivers, races, race_results, laps, users) |
| `prediction_service.py` | XGBoost (qualifying) + LightGBM (race finish) ML models; trains on DuckDB data |
| `redis_service.py` | Real Redis client for live state and pub/sub |
| `mock_redis_service.py` | In-memory Redis mock (used when Redis is unreachable) |
| `fastf1_service.py` | FastF1 library wrapper (years 2020–2024) |
| `ergast_service.py` | Jolpica-Ergast REST API wrapper (other years) |
| `cache_service.py` | In-process cache layer for API responses |

**Data source routing**: `api/main.py` uses `FASTF1_YEARS = [2020, 2021, 2022, 2023, 2024]` to route to FastF1 vs Jolpica-Ergast.

**Redis fallback**: On startup, tries real Redis; silently falls back to `MockRedisService` if unreachable. App runs without Redis locally.

**DuckDB fallback**: `SimpleDuckDBService` falls back to in-memory dict if DuckDB is unavailable. Seeds sample data on startup via `_load_sample_data()`.

**Postgres (Supabase)**: Reads `DATABASE_URL` env var. If set, `PostgresService` initialises on startup. If unavailable or unset, auth endpoints are disabled gracefully (no crash).

### WebSocket live data flow

1. `live/poller.py` polls FastF1 for live session data → writes canonical `LiveState` to Redis via `set_live_state()` + `publish_update()`
2. `api/main.py:/ws/live/{race_id}` accepts WebSocket connections, sends initial state, streams Redis pub/sub messages; `_unwrap_live_state()` flattens Redis envelope so frontend always gets a flat `LiveState`
3. Frontend `LiveDataMonitor` connects to WebSocket with exponential backoff; `LiveAnalytics` polls REST every 15s

### Prediction service (`api/services/prediction_service.py`)

- **Training**: triggered on first predict call or via `POST /predict/train`
- **Qualifying model**: XGBoost Regressor — features: circuit avg qualifying position, rolling 5-race form
- **Race model**: LightGBM Regressor — features: grid position, circuit avg finish, rolling 5-race form, DNF rate
- **Grid data availability**: `_grid_available = grid_coverage > 0.5`; shown as status on Predictions page
- **Note**: bundled DuckDB has `grid = NULL` for existing rows — run `ingest/simple_ingest.py --years 2022 2023 2024` to populate

### Frontend routing (`src/App.tsx`)

```
/             → MainPage
/dashboard    → Dashboard (tabs: Overview | Drivers | Teams | Tracks | Race Results)
/predictions  → Predictions (ML qualifying + race predictions)
/live         → LiveAnalytics   (Live section, "Overview" tab)
/live-monitor → LiveDataMonitor (Live section, "Live Monitor" tab)
/lap-data     → LapData (not in the nav)
/data-manager → DataManager (admin only)
/race-results → redirect to /dashboard?tab=results
/drivers      → redirect to /dashboard?tab=drivers
/tracks       → redirect to /dashboard?tab=tracks
*             → redirect to /
```

The Dashboard keeps its state in the URL: `?tab=overview|drivers|teams|tracks|results&year=YYYY&gp=<GP token>` (e.g. `/dashboard?tab=results&year=2026&gp=Spanish`).

### Frontend UI kit (`src/components/ui/`)

Every page is built from the same components — use them for new pages instead of ad-hoc markup: `PageShell`/`PageHeader`/`FadeIn` (layout), `Card`/`CardHeader`/`StatCard`/`DetailList`, `Tabs`/`TabPanel`, `SelectField`/`TextField`/`FilterBar`/`Button`, `LoadingState`/`ErrorState`/`EmptyState`/`Notice`, `TableWrap`/`Th`/`Td`/`Tr`/`PositionBadge`/`TeamChip`, `Pill`. Style: dark `bg-gray-900` cards with `border-gray-800`, `racing-red` accent, Orbitron/Racing Sans One from the existing tailwind config. Tab-content components (Drivers/Tracks/Race Results) render inside the Dashboard shell — they must not add their own page wrapper or `<h1>`.

Conventions: never show made-up data when a request fails (use `ErrorState` with a retry), keep filters mounted while results load, and guard async loads with a request-id so a stale response can't overwrite a newer one. Date helpers live in `src/utils/dates.ts` (schedule dates are plain calendar days — don't `new Date("YYYY-MM-DD")` them). `src/services/backendApi.ts` only uses the committed `public/data/*` snapshots for finished seasons; the current season always comes from the live API.

`AuthProvider` wraps the app shell (required — components call `useAuth()`). Auth routes exist but content is not gated — shelved by user decision.

Navigation items: Home, Dashboard, Predictions, Live, Data Manager.

Frontend calls backend via `src/services/backendApi.ts` (base URL from `REACT_APP_API_URL`, defaulting to `http://localhost:8000`).

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `REDIS_URL` | `redis://localhost:6379` | Redis connection (Upstash in prod) |
| `DUCKDB_PATH` | `data/f1_history.duckdb` | DuckDB file path |
| `DATABASE_URL` | — | Supabase PostgreSQL connection string |
| `FASTF1_CACHE_DIR` | `data/fastf1_cache` | FastF1 session cache |
| `CORS_ORIGINS` | `http://localhost:3000,...` | Allowed CORS origins |
| `RACE_YEAR` / `RACE_GP` / `POLL_INTERVAL` | 2024 / Bahrain / 5 | For `live/poller.py` |
| `API_BASE_URL` | `http://localhost:8000` | Where `live/poller.py` calls back to trigger post-race ingest |
| `INTERNAL_API_KEY` | — | Shared secret so `live/poller.py` can call `POST /admin/ingest/race` without a user login |
| `REACT_APP_API_URL` | `http://localhost:8000` | Frontend API base URL |
| `JWT_SECRET` | — | Auth JWT signing key — see `CLAUDE.local.md` |
| `SUPABASE_ACCESS_TOKEN` | — | Optional; lets `scripts/health_poller.py` restore a paused Supabase project (project ref is parsed from `DATABASE_URL`, or set `SUPABASE_PROJECT_REF`) |
| `LOG_FORMAT` | plain text | Set to `json` for structured JSON logging |
| `LOG_LEVEL` | `INFO` | Logging level |

### Key API endpoints

- `GET /health` — service health + Redis/DuckDB probe
- `GET /drivers`, `GET /races` — historical data (DuckDB → FastF1/Ergast fallback)
- `GET /race/{race_id}/results`, `/race/{race_id}/laps` — race detail
- `GET /live/{race_id}/state` — current live state from Redis
- `WS /ws/live/{race_id}` — WebSocket live updates
- `GET /api/drivers`, `/api/constructors`, `/api/races` — legacy endpoints (frontend uses these)
- `POST /simulate/live/{race_id}` — inject mock live state for testing
- `GET /predict/status` — ML model readiness + grid data availability flag
- `GET /predict/circuits` — circuits available for prediction
- `GET /predict/qualifying/{circuit}` — qualifying position predictions
- `GET /predict/race/{circuit}` — race finish predictions
- `POST /predict/train` — re-train models on latest DuckDB data
- `POST /auth/signup`, `POST /auth/login`, `GET /auth/me` — JWT auth

### Development notes

- **CI is shelved** — no `.github/workflows/ci.yml`; run tests manually with `pytest`
- **`api/requirements.txt`** lives at `api/` (not repo root) — prevents Render static site builder from auto-installing Python deps on the frontend build
- **`venv/`** is committed (large; adds noise to `git status`) — ignore modified `venv/` entries
- **DuckDB file** is committed and bundled in Docker; migration to Supabase is the next major infra task
- **Incremental commits, no push** until user approves — user preference
