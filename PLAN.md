# Shif1 UP — Build Plan

## Current State (as of 2026-05-21)

### What's working
- React/TypeScript frontend deployed as Render Static Site
- FastAPI backend deployed as Render Docker Web Service
- Dashboard with sub-tabs: Overview, Drivers, Teams, Tracks
- Navigation: Home, Dashboard, Predictions, Race Results, Live, Data Manager
- Race Predictions page — ML-powered qualifying + race finish predictions (XGBoost + LightGBM)
- DuckDB bundled historical F1 data (2020–2024 via FastF1 / Jolpica-Ergast)
- Upstash Redis for live race WebSocket streaming
- Supabase PostgreSQL wired (auth endpoints; F1 data migration approved but not yet done)
- Live Data Monitor with WebSocket reconnect + exponential backoff
- UI fully sanitized — no API names, timestamps, or infra details visible to users
- AuthProvider present in app shell; auth routes remain but are not enforced

### Remaining gaps
1. **F1 data → Supabase migration** — approved, not started; DuckDB bundled in Docker image for now
2. **Grid data missing in bundled DuckDB** — prediction accuracy limited; fix: run `ingest/simple_ingest.py --years 2022 2023 2024` and commit updated DuckDB, or complete Supabase migration
3. **Live end-to-end smoke test** — needs a real F1 session; mocked via `/simulate/live`
4. **Supabase CORS** — update `CORS_ORIGINS` on Render once stable frontend URL is confirmed

---

## Phase 1 — Stabilize the Foundation ✅

- [x] Consolidate `backend/` and `api/` into a single FastAPI app (`api/main:app`)
- [x] Fix `backendApi.ts` URL mismatches
- [x] CORS configured via `CORS_ORIGINS` env var
- [x] Redis graceful fallback — real Redis attempted, falls back to `MockRedisService`

---

## Phase 2 — Real Auth ✅ (shelved in UI, code retained)

- [x] JWT auth (`python-jose` + `passlib`) — `POST /auth/signup`, `POST /auth/login`, `GET /auth/me`
- [x] Users stored in DuckDB `users` table
- [x] `AuthContext.tsx` calls backend; JWT stored in localStorage
- [x] `AuthProvider` wraps app shell (required — components call `useAuth()`)
- [x] Auth routes exist but navigation does not gate content (shelved by user decision)

---

## Phase 3 — Data Layer ✅

- [x] Ingest 2024 season via `ingest/simple_ingest.py`
- [x] Fixed DuckDB `store_*` bug (`executemany()` + positional params)
- [x] Fixed data source routing: FastF1 for 2020–2024, Jolpica-Ergast for others
- [x] Race Results, Driver Analytics, Track Analytics served from real data
- [ ] Lap Data — empty until lap telemetry is ingested (needs `session.load(laps=True)`)

---

## Phase 4 — Live Data ✅ (pending real-session smoke test)

- [x] `live/poller.py` emits canonical `LiveState` shape to Redis
- [x] WS `/ws/live/{race_id}` delivers flat `LiveState` (envelope unwrapped server-side)
- [x] `LiveDataMonitor.tsx` — WebSocket connect/reconnect with exponential backoff
- [x] `LiveAnalytics.tsx` — polls live state every 15s, renders positions when session is live
- [x] `/simulate/live/{race_id}` for local testing
- [ ] End-to-end smoke test during a real F1 session

---

## Phase 5 — Predictions ✅

**Goal:** ML-powered race outcome predictions from historical F1 data.

- [x] `grid` column added to `race_results` table (qualifying position — strongest predictor)
- [x] `api/services/prediction_service.py` — trains XGBoost (qualifying) + LightGBM (race) on DuckDB data
- [x] `GET /predict/qualifying/{circuit}` and `GET /predict/race/{circuit}`
- [x] `GET /predict/status` — reports model readiness and grid data availability
- [x] `GET /predict/circuits` — lists circuits available for prediction
- [x] `POST /predict/train` — re-trains models on latest DuckDB data
- [x] `Predictions.tsx` — circuit selector, Generate Predictions button, side-by-side quali/race tables
- [x] Model names hidden from UI (internal implementation detail)
- [ ] Re-ingest 2022–2024 to populate `grid` column (existing rows have `grid = NULL`)

**Models:**
- Qualifying: XGBoost Regressor (circuit avg quali, rolling 5-race form)
- Race: LightGBM Regressor (grid position, circuit avg finish, rolling form, DNF rate)

---

## Phase 6 — Production Readiness ✅

- [x] Rate limiting — `slowapi` at 60/min general, 10/min auth/simulate endpoints
- [x] Structured logging — `LOG_FORMAT=json` env var; `LOG_LEVEL` controls level
- [x] Secrets audit — only `JWT_SECRET` has a dev fallback (logs warning)
- [x] `/health` hardened — independent Redis + DuckDB probes, 503 only on DuckDB failure
- [x] CI — **shelved** by user decision; `.github/workflows/ci.yml` deleted
- [x] Navbar unified and simplified
- [x] Dashboard refactored to sub-tabs (Overview / Drivers / Teams / Tracks)
- [x] Drivers and Tracks removed from top-level navigation
- [x] UI sanitized — no API names, data sources, timestamps, or infra details visible
- [x] Backend deployed to Render (Docker Web Service)
- [x] Frontend deployed to Render (Static Site)
- [x] `public/_redirects` for React Router on Render static hosting

---

## Hosting — Current Stack

| Service | What it hosts | Notes |
|---------|--------------|-------|
| **Render** (Docker) | FastAPI backend | Free tier; `env: docker`; `api/requirements.txt` |
| **Render** (Static Site) | React frontend | Auto-builds on push; `public/_redirects` for SPA routing |
| **Supabase** | PostgreSQL | Auth users table; F1 data migration planned |
| **Upstash** | Redis | Live race WebSocket state only; 10K cmds/day free |
| **DuckDB** | Historical F1 data | Bundled in Docker image (`/app/data/f1_history.duckdb`) |

### Architecture

```
Browser
  │
  ├── React app (Render Static Site — CDN)
  │
  └── FastAPI (Render Docker Web Service)
        ├── Auth → Supabase Postgres (users table)
        ├── F1 historical data → DuckDB (bundled in container)
        │   └── planned: migrate to Supabase Postgres
        ├── Live state → Upstash Redis
        └── WebSocket → same Render service (WS supported on free tier)
```

### Render YAML (`render.yaml`)
```yaml
services:
  - type: web
    name: shif1-up-api
    env: docker
    dockerfilePath: ./Dockerfile
    dockerContext: .
    envVars:
      - key: DUCKDB_PATH
        value: /app/data/f1_history.duckdb
      - key: REDIS_URL
        sync: false       # set in Render dashboard: Upstash Redis URL
      - key: DATABASE_URL
        sync: false       # set in Render dashboard: Supabase connection string
      - key: CORS_ORIGINS
        sync: false       # set in Render dashboard: https://<frontend>.onrender.com
  - type: web
    name: shif1-up-frontend
    env: static
    buildCommand: npm ci && npm run build
    staticPublishPath: ./build
    envVars:
      - key: REACT_APP_API_URL
        sync: false       # set in Render dashboard: https://<backend>.onrender.com
```

---

## Phase 7 — F1 Data Migration to Supabase (approved, not started)

**Goal:** Move historical F1 data out of the bundled DuckDB file into Supabase PostgreSQL so ingest can run without committing large binary files to Git.

- [ ] Create `api/services/supabase_f1_service.py` — drop-in replacement for `SimpleDuckDBService`
- [ ] Update `api/main.py` to use `SupabaseF1Service` when `DATABASE_URL` is set
- [ ] Update `ingest/simple_ingest.py` to write to Supabase
- [ ] Run schema migration in Supabase dashboard (tables: `drivers`, `races`, `race_results`, `laps`)
- [ ] Ingest 2022–2024 data (including `grid` column) into Supabase
- [ ] Remove DuckDB file from Docker image once migration is complete

---

## Phase 8 — Cleanup

- [ ] Delete `backend/` — dead code
- [ ] Delete `api/simple_main.py`, `api/enhanced_main.py`, `api/working_enhanced_main.py`
- [ ] Remove `bcryptjs` frontend dependency
- [ ] Remove `venv/` from git tracking (large binary)
- [ ] Update `.gitignore` for `__pycache__/`, `*.pyc`, `.venv/`, `venv/`, `api/cache/`, `data/fastf1_cache/`

---

## Future Enhancements

### Data & Analytics
- **Lap telemetry** — sector times, speed traces, tyre degradation; needs `historical_ingest.py` (hours-long FastF1 download)
- **Live timing detail** — sector splits, DRS/pit status per driver during live sessions
- **Constructor championship tracker** — points progression chart across the season
- **Head-to-head driver comparison** — side-by-side lap time distributions

### Predictions
- **Confidence intervals** — show uncertainty, not just a single finish order
- **Post-race model evaluation** — compare predicted vs actual finish, log accuracy over time
- **Tyre strategy integration** — use compound data as a prediction feature

### Infrastructure
- **Incremental ingest automation** — trigger after each race weekend via scheduled job
- **Real Redis in production** — Upstash is already wired; mock fallback for local dev only

### UX / Frontend
- **Lap Data page** — populate from ingested lap rows
- **Push notifications** — notify when a live session starts or safety car is deployed
- **Mobile / PWA**

---

## Out of Scope (for now)
- Everything listed under Future Enhancements — deliberately deferred, not forgotten
