# Shif1 UP — Technical Reference

> Living document. Updated as features are built. For the high-level build plan see `PLAN.md`.

---

## Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [Services & Ports](#services--ports)
3. [Database Schema](#database-schema)
4. [API Endpoints](#api-endpoints)
5. [Authentication](#authentication)
6. [ML Predictions](#ml-predictions)
7. [Live Data Pipeline](#live-data-pipeline)
8. [Hosting Stack](#hosting-stack)
9. [Admin Access](#admin-access)
10. [Environment Variables](#environment-variables)
11. [Running Locally](#running-locally)
12. [Data Ingestion](#data-ingestion)

---

## Architecture Overview

```
Browser
  ├── React (TypeScript, TailwindCSS, Chart.js)   http://localhost:3000
  │     └── src/services/backendApi.ts  ──────────► FastAPI
  │
  └── FastAPI (Python, uvicorn)                    http://localhost:8000
        ├── Auth          → DuckDB (users table)
        ├── F1 History    → DuckDB (races, results, laps)
        ├── Live State    → Redis (real) / MockRedis (dev fallback)
        ├── ML Models     → in-process, persisted to data/models/
        └── External      → FastF1 (2020–2024), Jolpica/Ergast (other years)
```

---

## Services & Ports

| Service | Local URL | Notes |
|---|---|---|
| React frontend | `http://localhost:3000` | `npm start` |
| FastAPI backend | `http://localhost:8000` | `uvicorn api.main:app --reload` |
| Swagger UI | `http://localhost:8000/docs` | Interactive API explorer |
| ReDoc | `http://localhost:8000/redoc` | API reference docs |
| DuckDB | file: `data/f1_history.duckdb` | Embedded, no server |
| Redis | `redis://localhost:6379` | Falls back to in-memory mock if unavailable |

**Useful direct API URLs (browser):**
```
http://localhost:8000/health
http://localhost:8000/admin/db/stats
http://localhost:8000/admin/ingest/status
http://localhost:8000/predict/status
http://localhost:8000/api/cache/stats
```

---

## Database Schema

### DuckDB — `data/f1_history.duckdb`

#### `drivers`
| Column | Type | Notes |
|---|---|---|
| driver_id | VARCHAR PK | e.g. `"verstappen"` |
| full_name | VARCHAR | |
| nationality | VARCHAR | |
| number | INTEGER | car number |

#### `constructors`
| Column | Type | Notes |
|---|---|---|
| constructor_id | VARCHAR PK | e.g. `"red_bull"` |
| constructor_name | VARCHAR | |
| nationality | VARCHAR | |

#### `races`
| Column | Type | Notes |
|---|---|---|
| race_id | VARCHAR PK | format: `"{year}_{gp}"` e.g. `"2024_Bahrain"` |
| year | INTEGER | |
| round | INTEGER | round number in season |
| gp | VARCHAR | GP name |
| date | DATE | |
| circuit_name | VARCHAR | |
| country | VARCHAR | |

#### `race_results`
| Column | Type | Notes |
|---|---|---|
| race_id | VARCHAR | FK → races |
| position | INTEGER | finishing position |
| driver_id | VARCHAR | FK → drivers |
| constructor_id | VARCHAR | FK → constructors |
| grid | INTEGER | qualifying/starting position (Phase 5 addition) |
| points | FLOAT | |
| time | VARCHAR | e.g. `"1:31:44.742"` or `"+22.457"` |
| fastest_lap | BOOLEAN | |
| fastest_lap_time | VARCHAR | |
| status | VARCHAR | `"Finished"`, `"+1 Lap"`, `"DNF"`, etc. |
| PK | (race_id, position) | composite |

#### `laps`
| Column | Type | Notes |
|---|---|---|
| race_id | VARCHAR | |
| driver_id | VARCHAR | |
| lap_number | INTEGER | |
| lap_time_ms | INTEGER | milliseconds |
| sector1_ms | INTEGER | |
| sector2_ms | INTEGER | |
| sector3_ms | INTEGER | |
| tyre | VARCHAR | `"SOFT"`, `"MEDIUM"`, `"HARD"`, etc. |
| pit | BOOLEAN | pit stop on this lap |
| position | INTEGER | position at end of lap |
| PK | (race_id, driver_id, lap_number) | composite |

#### `users`
| Column | Type | Notes |
|---|---|---|
| id | VARCHAR PK | UUID |
| username | VARCHAR UNIQUE | |
| email | VARCHAR UNIQUE | |
| hashed_password | VARCHAR | bcrypt via passlib |
| preferences | JSON | user settings |
| is_admin | BOOLEAN | default FALSE |

**Schema migrations** (applied automatically on startup via `_create_tables`):
- Phase 5: `ALTER TABLE race_results ADD COLUMN grid INTEGER` — added if missing

---

## API Endpoints

### Auth
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/auth/signup` | — | Create account, returns JWT |
| POST | `/auth/login` | — | Login, returns JWT |
| GET | `/auth/me` | JWT | Current user info |
| PATCH | `/auth/me/preferences` | JWT | Update preferences |

### Data
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/drivers` | — | All drivers (optional `?year=`) |
| GET | `/drivers/{id}` | — | Driver details |
| GET | `/races` | — | Race schedule (optional `?year=`) |
| GET | `/race/{race_id}/results` | — | Race results |
| GET | `/race/{race_id}/laps` | — | Lap data (optional `?driver=`) |

### Live
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/live/{race_id}/state` | — | Current live state from Redis |
| WS | `/ws/live/{race_id}` | — | WebSocket live updates |
| POST | `/simulate/live/{race_id}` | — | Inject mock live state (dev only) |

### Predictions
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/predict/status` | — | Model training status + metadata |
| GET | `/predict/circuits` | — | Available circuits for prediction |
| GET | `/predict/qualifying?circuit=X` | — | Qualifying position predictions |
| GET | `/predict/race?circuit=X` | — | Race finish predictions |
| POST | `/predict/train` | — | Retrain models (background task) |

### Admin
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/admin/db/stats` | — | Row counts per table |
| POST | `/admin/ingest` | — | Trigger data ingest |
| GET | `/admin/ingest/status` | — | Ingest job progress |
| GET | `/health` | — | Service health (Redis + DuckDB) |

### Legacy (frontend uses these)
| Method | Path | Description |
|---|---|---|
| GET | `/api/drivers` | Driver standings |
| GET | `/api/constructors` | Constructor standings |
| GET | `/api/races` | Race schedule |

---

## Authentication

- **Method**: JWT (JSON Web Tokens) via `python-jose`
- **Storage**: `localStorage` on the frontend (XSS risk acceptable at current scale)
- **Password hashing**: `passlib[bcrypt]`
- **Token lifetime**: configured via `JWT_SECRET` env var
- **Guard**: `get_current_user` FastAPI Depends on protected endpoints

**Admin account**: `eli1` / (password set separately — ask Claude to reset if forgotten)

---

## ML Predictions

### Models
| Task | Model | Library | Features |
|---|---|---|---|
| Qualifying position | XGBoost Regressor | `xgboost` | Driver/team circuit avg grid, rolling 5-race grid form |
| Race finish position | LightGBM Regressor | `lightgbm` | Predicted grid, driver/team circuit avg finish, rolling form, DNF rate |

### Time Weighting
Training uses **exponential decay by year** via `sample_weight` in both XGBoost and LightGBM `fit()` calls. Decay factor = **1.5**:

| Year | Sample Weight | Rationale |
|---|---|---|
| 2020 | 1.0× | COVID season, different regulations |
| 2021 | 1.5× | |
| 2022 | 2.25× | Ground-effect regulation change |
| 2023 | 3.4× | |
| 2024 | 5.1× | Most recent, highest influence |

Formula: `weight = 1.5 ^ (year - min_year)` — implemented in `_time_weights()` in `prediction_service.py`.
2024 has ~5× the influence of 2020. Decay factor of 1.5 is deliberately conservative — 2.0 would overfit to the most recent season.

### Feature Engineering
```
qualifying_features = [
    driver_rolling_grid,        # rolling 5-race avg qualifying position
    driver_circuit_grid_avg,    # historical avg qualifying at this circuit
    constructor_rolling_finish, # team rolling form
    constructor_circuit_avg,    # team avg at this circuit
    driver_enc, constructor_enc, circuit_enc,  # label-encoded categoricals
    round                       # circuit round number
]

race_features = [
    grid,                       # qualifying position (predicted or actual)
    driver_rolling_finish,      # rolling 5-race avg finish
    driver_circuit_avg,         # historical avg finish at this circuit
    constructor_rolling_finish,
    constructor_circuit_avg,
    driver_dnf_rate,            # rolling 10-race DNF rate
    driver_enc, constructor_enc, circuit_enc,
    round
]
```
> When `grid` is NULL (pre-re-ingest), `grid` is dropped from race features automatically.

### Model Persistence
Models are saved to `data/models/` after each training run using `joblib`:
```
data/models/
  race_model.pkl      # LightGBM regressor
  quali_model.pkl     # XGBoost regressor
  encoders.pkl        # label encoder class lists + driver/constructor/circuit maps
  meta.json           # training metadata (date, rows, years, decay factor, grid coverage)
```

**Startup behaviour**: On every restart, `prediction_service.load_from_disk()` is called in `lifespan`. If models exist → loaded immediately, no retrain. If missing → models train on first `/predict/*` request.

**Directory**: configurable via `MODEL_DIR` env var (default: `data/models`). In production (Fly.io), this directory lives on the persistent volume alongside DuckDB so models survive deploys.

**`/predict/status` response includes**:
```json
{
  "trained": true,
  "race_model_ready": true,
  "quali_model_ready": false,
  "grid_data_available": false,
  "training_rows": 479,
  "circuits": 25,
  "years": [2024],
  "trained_at": "2026-04-22T16:00:00",
  "decay_factor": 1.5,
  "grid_coverage": "0%"
}
```

### Data Requirements
- **Minimum**: 20 rows with non-null features to train
- **Recommended**: 2020–2024 (~2,000+ rows) — ingest via Data Manager
- **Grid data**: Re-ingest after Phase 5 `simple_ingest.py` update to populate `grid` column
- **Qualifying model**: requires `grid` column to be populated (NULL = model skipped)

### Retraining
- Auto-trains on first `/predict/*` request if no saved models found
- Force retrain: POST `/predict/train` or click "Retrain Models" in the UI
- Should retrain after any new data ingest

---

## Live Data Pipeline

```
live/poller.py
  └── polls FastF1 every 5s during a live session
  └── writes to Redis: set_live_state() + publish_update()

api/main.py:/ws/live/{race_id}
  └── accepts WebSocket connections
  └── sends initial state from Redis
  └── streams Redis pub/sub messages → frontend

Frontend LiveDataMonitor / LiveAnalytics
  └── connects to WS, exponential backoff reconnect
  └── LiveAnalytics polls /live/{race_id}/state every 15s as fallback
```

**Redis envelope format** (internal):
- Stored: `{race_id, timestamp, state: {...LiveState}}`
- Published: `{race_id, timestamp, update: {type, state: {...}}}`
- `_unwrap_live_state()` in `main.py` flattens both → flat `LiveState` for the frontend

---

## Hosting Stack

### Production (planned — Phase 6 deploy)

| Service | What | Free Tier |
|---|---|---|
| **Vercel** | React frontend | Unlimited personal projects |
| **Fly.io** | FastAPI backend + DuckDB persistent volume | 3 shared VMs, 3 GB storage |
| **Supabase** | PostgreSQL — users/auth table only | 500 MB, 2 projects |
| **Upstash** | Redis — live race state + WebSocket pub/sub | 10,000 commands/day |

### Architecture in production
```
Browser
  ├── React (Vercel CDN)
  └── FastAPI (Fly.io)
        ├── Auth        → Supabase Postgres (users table only)
        ├── F1 History  → DuckDB on Fly.io persistent volume (/app/data)
        ├── ML Models   → same Fly.io volume (/app/data/models/)
        ├── Live state  → Upstash Redis
        └── WebSocket   → Fly.io (supports WS on free tier)
```

### ML models in production
- Run **in-process on Fly.io** alongside FastAPI — no separate ML service needed
- Models persisted to Fly.io persistent volume at `/app/data/models/` → survive restarts and deploys without retraining
- RAM usage: ~30–50 MB for training on 5 years (~2,000 rows) — well within 256 MB free tier
- Training time: < 10s for 5 years of data
- Startup: loads from disk in `lifespan` → API is warm immediately with no cold retrain delay

### Why not a separate ML service?
Dataset is ~2,000 rows. XGBoost + LightGBM train in < 10s, infer in < 50ms. A separate service (e.g. SageMaker, Vertex AI) would add latency, cost, and operational complexity for no benefit at this scale.

---

## Admin Access

### App admin account
- **Username**: `eli1`
- **Email**: `eli1@gmail.com`
- **is_admin**: `true`
- Password: set by user (reset via Claude if forgotten)

### Admin pages / interfaces
| Interface | URL | Notes |
|---|---|---|
| Data Manager | `http://localhost:3000/data-manager` | Ingest control, DB stats, cache |
| Swagger UI | `http://localhost:8000/docs` | Full API explorer with JWT auth |
| ReDoc | `http://localhost:8000/redoc` | API reference |
| Health check | `http://localhost:8000/health` | Redis + DuckDB status |
| DB stats | `http://localhost:8000/admin/db/stats` | Row counts per table |

> DuckDB, FastF1, and Ergast have no web admin. Use the Data Manager or direct Python queries.

---

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `REDIS_URL` | `redis://localhost:6379` | Redis connection (falls back to mock) |
| `DUCKDB_PATH` | `data/f1_history.duckdb` | DuckDB file path |
| `FASTF1_CACHE_DIR` | `data/fastf1_cache` | FastF1 session cache directory |
| `CORS_ORIGINS` | `http://localhost:3000,...` | Allowed CORS origins (comma-separated) |
| `JWT_SECRET` | `dev-secret-change-in-production` | **Change in production** — logs warning if default |
| `RATE_LIMIT` | `60/minute` | General rate limit |
| `RATE_LIMIT_AUTH` | `10/minute` | Auth endpoint rate limit |
| `LOG_FORMAT` | `text` | Set to `json` for structured production logging |
| `LOG_LEVEL` | `INFO` | Logging level |
| `RACE_YEAR` | — | For `live/poller.py` |
| `RACE_GP` | — | For `live/poller.py` |
| `REACT_APP_API_URL` | `http://localhost:8000` | Frontend API base URL |
| `MODEL_DIR` | `data/models` | ML model persistence dir (use `/app/data/models` on Fly.io) |

---

## Running Locally

```bash
# Backend
cd api
PYTHONIOENCODING=utf-8 ../venv/Scripts/uvicorn.exe main:app --reload --port 8000

# Frontend (separate terminal)
npm start

# Both together (if concurrently is installed)
npm run dev
```

> **Windows note**: `npm run dev` requires `concurrently` to be installed globally or in node_modules.
> If it fails, start backend and frontend in separate terminals.

---

## Data Ingestion

### Fast ingest (recommended — minutes)
```bash
# Single year
python ingest/simple_ingest.py --years 2024

# Multiple years (recommended for ML — 5 years)
python ingest/simple_ingest.py --years 2020 2021 2022 2023 2024
```
Captures: race results, driver standings, constructor standings, qualifying grid positions.
Does NOT capture: lap-level telemetry, sector times.

### Full ingest with telemetry (hours)
```bash
python ingest/historical_ingest.py --years 2024
```
Adds: lap times, sector splits (S1/S2/S3 ms), tyre compounds, pit stops.
Required for: Lap Data page, sector-level ML features.

### Via the app (Data Manager page)
1. Go to `http://localhost:3000/data-manager`
2. Enter years (e.g. `2020 2021 2022 2023 2024`)
3. Click "Start Ingest"
4. Monitor progress at `http://localhost:8000/admin/ingest/status`

### After ingest
- Retrain ML models: POST `/predict/train` or click "Retrain Models" on the Predictions page
- Models auto-detect grid data availability and enable qualifying predictions if grid is populated

---

*Last updated: 2026-04-22*
