# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **Secrets**: actual service URLs, connection strings, and API keys live in `CLAUDE.local.md` (gitignored — never committed).

## Commands

### Run everything (recommended for development)
```bash
npm run dev          # Starts both backend + frontend concurrently
npm run up           # Same, but supervised: health-checks both and restarts whichever stops responding
```

`scripts/health_poller.py` (stdlib only; `--check` prints status and exits, `--only backend|frontend`). It adopts servers that are already healthy, writes child output to `logs/`, and restarts whichever stops responding. A backend running against Supabase heals its own database connection (see `DatabaseGuardian` below), so the poller reports that state but doesn't restart for it; an older backend that reports `degraded` without the self-healing marker is still restarted, and `SUPABASE_ACCESS_TOKEN` (in `.env`) lets the poller restore a paused project for such a backend. A running poller also keeps a free-tier project from re-pausing, since `/health` runs `SELECT 1`.

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
RACE_YEAR=2024 RACE_GP=Bahrain python live/poller.py                  # the race
RACE_YEAR=2024 RACE_GP=Bahrain python live/poller.py --session Q      # FP1 FP2 FP3 SQ S Q R
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

Config in `render.yaml`. Secrets (`REDIS_URL`, `DATABASE_URL`, `CORS_ORIGINS`, `SUPABASE_ACCESS_TOKEN`, `REACT_APP_API_URL`) are set in the Render dashboard — never committed. `REACT_APP_API_URL` is read at **build** time (CRA bakes it into the bundle), so changing it needs a frontend redeploy; if it's missing the site falls back to `http://localhost:8000`. Render's CI build treats lint warnings as errors, so check with `CI=true npm run build` before pushing.

**Cold starts and paused databases**: on the free plan the API host sleeps after ~15 min idle and a free Supabase project pauses after a week idle. Opening the site wakes both: the frontend pings `/health` on load, which boots the API; the API's `DatabaseGuardian` then reconnects to Supabase and, if the project is paused, restores it via the Management API (needs `SUPABASE_ACCESS_TOKEN`). Until the API **and** its database are ready the frontend shows a blurred full-screen wait screen (`ServiceGate`) instead of pages — steps, a timer and a "Last check" line that says exactly what the last `/health` call returned; after 2 minutes it offers *Try again* / *Open the site anyway* so it can never trap a visitor. Database-backed endpoints answer `503 database_waking` meanwhile. Once the site has loaded, a later outage shows a slim banner (`ServiceStatusBanner`) and remounts the routes when it recovers.

`/health` `checks.database` reports `state`, `project_status` (what Supabase's API says: `INACTIVE`, `PAUSING`, …) and `can_restore` (whether a token is configured) — check it first when a wake-up doesn't happen: `state: unavailable` with `can_restore: false` means the server has no token, and `unavailable` with a token means Supabase reports a status the guardian can't act on (its `project_status` says which). A failing DB probe makes `/health` verify the connection immediately, so a project paused under a running API is noticed on the next page load, not at the next 60s keepalive.

### Backend service layer (`api/services/`)

| Service | Purpose |
|---|---|
| `simple_duckdb_service.py` | DuckDB historical F1 storage (drivers, races, race_results, laps, users) |
| `prediction_service.py` | LightGBM rankers (qualifying, race, sprint); walk-forward backtest; trains on the F1 database |
| `redis_service.py` | Real Redis client for live state and pub/sub |
| `mock_redis_service.py` | In-memory Redis mock (used when Redis is unreachable) |
| `fastf1_service.py` | FastF1 library wrapper (years 2020–2024) |
| `ergast_service.py` | Jolpica-Ergast REST API wrapper (other years) |
| `cache_service.py` | In-process cache layer for API responses |
| `db_guardian.py` | Owns the Supabase connection: connects in the background, wakes a paused project, reconnects if it drops |
| `redact.py` | `redact_url()` — keep credentials (e.g. the Upstash token) out of logs |

**Data source routing**: `api/main.py` uses `FASTF1_YEARS = [2020, 2021, 2022, 2023, 2024]` to route to FastF1 vs Jolpica-Ergast.

**Redis fallback**: On startup, tries real Redis; silently falls back to `MockRedisService` if unreachable. App runs without Redis locally.

**DuckDB fallback**: `SimpleDuckDBService` falls back to in-memory dict if DuckDB is unavailable. Seeds sample data on startup via `_load_sample_data()`.

**Postgres (Supabase)**: reads `DATABASE_URL`. When set, `DatabaseGuardian` (`services/db_guardian.py`) opens both the auth and F1-data pools — the first attempt at startup (bounded), then retrying in the background — so the API always comes up and can answer `/health` even when the project is paused. If the connection fails and `SUPABASE_ACCESS_TOKEN` is set it asks Supabase's Management API for the project state and restores it if paused, then reconnects without a restart (`SUPABASE_PROJECT_REF` is otherwise parsed from `DATABASE_URL`; `SUPABASE_API_URL` overrides the API host, for tests). While it's down, DB-backed endpoints (`/race/*`, `/predict/*` except status/circuits, `/admin/*`, `/auth/*`) answer `503 {"detail": "database_waking"}` with `Retry-After` and CORS headers. Unset `DATABASE_URL` means local DuckDB with auth disabled. `_run_query` swallows errors and returns `[]`, so don't use it to test connectivity.

### WebSocket live data flow

1. `live/poller.py` polls FastF1 for **one session per process** (`--session`, default `R`) → writes `LiveState` to Redis via `set_live_state()` + `publish_update()`. Start one poller per session you want to follow. The race id is `{year}_{gp}`; other sessions get a suffix (`2026_Belgian_Grand_Prix_FP1`) — ids are opaque to the API, Redis and WebSocket. Existing limitation: the poller calls `session.load()` and treats non-empty results as "live"; it is not a true live-timing client
2. Two state shapes, marked by `session_type`: **classified** (`R`, `S`) — FastF1 race `Position` order plus a lap counter; **timed** (`FP1-3`, `SQ`, `Q`) — ordered by best lap so far with gap to the fastest, no lap counter. Both are built from one `build_driver_rows()`, so every driver carries the same timing-board fields: `best_lap_time` + `best_lap_status` (`purple` = session fastest, else `green`), `sectors` (latest lap's S1–S3, each `purple` session best / `green` own best / `yellow` slower / `none` not set), `tyre`, `tyre_age`, `stints`, `in_pit` (dims the row), `team`, `laps_completed`; drivers with no timed lap are listed last ("No time"). Timed sessions have no classification to wait for, so they end after 5 minutes with no new lap; the end-of-session ingest sends the session
3. `api/main.py:/ws/live/{race_id}` accepts WebSocket connections, sends initial state, streams Redis pub/sub messages; `_unwrap_live_state()` flattens Redis envelope so frontend always gets a flat `LiveState`. `POST /simulate/live/{race_id}?session=...` writes either shape for local testing (22-car field for timed sessions)
4. Frontend `LiveDataMonitor` has a Session select (Practice 1-3, Qualifying, Race; a sprint weekend — `RaceEvent.is_sprint` — is Practice 1, Sprint Qualifying, Sprint, Qualifying, Race), connects with exponential backoff, and renders `LiveTimingBoard` (a live-timing style board with **Laps / Sectors / Tyres** tabs; no *Segments* tab — those mini-sector bars need live telemetry that FastF1's lap data doesn't include). Qualifying and sprint qualifying add knockout-zone headers (Q3 = top 10, then six out in Q2, six out in Q1 on a 22-car grid; `qualifyingZone` in `utils/races.ts`) from the *current best-lap order* — exact for the final order, but mid-session eliminated drivers keep their Q1 laps. Sector/tyre data only changes when a lap completes, so the board lags the official timing screen. `LiveAnalytics` polls REST every 15s and follows the race only

### Prediction service (`api/services/prediction_service.py`)

- **Training**: starts in the background as soon as the database is ready (`_warm_prediction_models`, fired by `DatabaseGuardian`'s `on_ready` hook; local DuckDB starts it at boot), or on the first predict call, or via `POST /predict/train`. It is single-flight (`_train_lock`: the three parallel predictions on the Predictions page share one training) and the CPU-bound fit (`_fit`) runs in a worker thread on a private copy of the state that is swapped in atomically — the event loop, and so `/health`, stays responsive. Models are saved to `MODEL_DIR`, which is temporary storage on Render's free plan, so every cold start retrains (~10s locally); `/predict/status` reports `training` while it runs and the frontend shows "Models warming up" until `trained`
- **Models**: qualifying, race and sprint are all `LGBMRanker` (lambdarank), grouped per race — a ranking objective, so predictions display as plain rank (#1, #2, …) with no fractional "expected position". `_fit_ranker` turns position/grid into a per-race relevance score (`field_size + 1 - value`, clipped ≥ 0; LightGBM rejects negative labels) and `_ranks_from_scores` turns scores back into ranks. Race/sprint predictions feed the qualifying *rank* in as their grid input
- **Features**: rolling 5-race form, circuit history, constructor form, DNF rate, grid (see `RACE_FEATURES_*`, `QUALI_FEATURES`), plus `driver_practice_best_rank` (best FP1–3 rank that weekend) — only active once >50% of rows have it (`_practice_available`). Practice comes from `POST /admin/ingest` with `practice: true` (off by default; slow, and FastF1's timing API can fail partway). Upcoming-race predictions leave it NaN (no practice yet)
- **Accuracy**: `GET /predict/backtest` serves the cached **walk-forward** result (each season scored by a model trained only on earlier seasons — the honest number, roughly 3.9 quali / 3.5 race rank error) and falls back to scoring the live model against its own training data (~3x too optimistic) only when none is cached. Compute it with `POST /predict/backtest/refresh` (admin, background, ~3–4 refits); it's stored in `prediction_cache` under `_walkforward`, which `clear_prediction_cache()` deliberately keeps. Re-run it after changing features or ingesting data
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
| `RACE_YEAR` / `RACE_GP` / `RACE_SESSION` / `POLL_INTERVAL` | 2024 / Bahrain / R / 5 | For `live/poller.py`. `RACE_SESSION` (or `--session`) is one of `FP1 FP2 FP3 SQ S Q R` |
| `API_BASE_URL` | `http://localhost:8000` | Where `live/poller.py` calls back to trigger post-race ingest |
| `INTERNAL_API_KEY` | — | Shared secret so `live/poller.py` can call `POST /admin/ingest/race` without a user login |
| `REACT_APP_API_URL` | `http://localhost:8000` | Frontend API base URL |
| `JWT_SECRET` | — | Auth JWT signing key — see `CLAUDE.local.md` |
| `SUPABASE_ACCESS_TOKEN` | — | **Set in production.** Lets the API (`db_guardian.py`) and `scripts/health_poller.py` restore a paused Supabase project (Supabase dashboard → Account → Access Tokens). Optional `SUPABASE_PROJECT_REF` (else parsed from `DATABASE_URL`) and `SUPABASE_API_URL` (test override) |
| `LOG_FORMAT` | plain text | Set to `json` for structured JSON logging |
| `LOG_LEVEL` | `INFO` | Logging level |

### Key API endpoints

- `GET /health` — service health: Redis + DB probes, plus `checks.database.state` (`ready` / `connecting` / `waking` / `unavailable`) when running against Supabase. Never gated; a request while the DB is down nudges the guardian to retry
- `GET /drivers`, `GET /races` — historical data (DuckDB → FastF1/Ergast fallback)
- `GET /race/{race_id}/results`, `/race/{race_id}/laps` — race detail
- `GET /live/{race_id}/state` — current live state from Redis
- `WS /ws/live/{race_id}` — WebSocket live updates
- `GET /api/drivers`, `/api/constructors`, `/api/races` — legacy endpoints (frontend uses these). Standings for years served by Jolpica (2025+) are fetched with `strict=True` and go through `_standings_or_stale`: up to 3 attempts within an 8s budget, then the last good copy, then `503 {"detail": "source_unavailable"}` — never a silent `200 []` (Jolpica rate-limits by IP and Render's free instances share one). A source that answers with no standings yet still returns `[]`. The frontend caches empty lists for ≤15s, not the full TTL
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
