# Shif1 UP — Build Plan

## Current State

### What's working
- React/TypeScript frontend with full routing (Dashboard, Driver Analytics, Track Analytics, Live Analytics, Race Results, Lap Data, Data Manager, Live Monitor)
- **Backend JWT auth** — `POST /auth/signup`, `POST /auth/login`, `GET /auth/me`; users stored in DuckDB; `AuthContext.tsx` calls the backend (IndexedDB/localStorage auth removed)
- Single FastAPI app (`api/main:app`) — `backend/` dir is dead code (Phase 7 cleanup target)
- DuckDB populated with 2024 season: 29 drivers, 25 races, 479 race results (lap telemetry excluded from fast ingest)
- Redis graceful fallback — real Redis attempted on startup, falls back to MockRedisService
- WebSocket live data (`/ws/live/{race_id}`) — flat envelope delivery confirmed working via tests
- Unified Navigation component — auth-gated items visible to everyone, redirect to `/login` with context banner when clicked while signed out
- Rate limiting (slowapi), structured JSON logging, CI (GitHub Actions), hardened `/health`

### Remaining gaps
1. **ML predictions are a stub** — `predict/worker.py` exists but no real model (Phase 5)
2. **Redis is mocked in dev** — `mock_redis_service.py` used locally; needs Upstash or real Redis for production (Phase 6 deploy)
3. **Lap telemetry** — deferred as a future enhancement; `simple_ingest.py` intentionally skips it; full sector times / speed traces would need `historical_ingest.py` (hours-long download)

---

## Phase 1 — Stabilize the Foundation ✅

**Goal:** One clean, working backend that the frontend reliably talks to.

- [x] Consolidate `backend/` and `api/` into a single FastAPI app — `start_backend.py` runs `api.main:app`; `backend/` dir left in place (deletion deferred to Phase 7 cleanup)
- [x] Confirm `start_backend.py` launches the correct app (`api.main:app`)
- [x] Verify all frontend `backendApi.ts` endpoint paths match backend — fixed URL format mismatches: `getRaceResults`/`getSessionLaps` now use `{year}_{gp}` race_id format; `getDriverDetails` corrected to `/drivers/{id}`; `getCachedOrFetch` now handles both direct-array and `{success,data}`-wrapped responses
- [x] CORS configured — `CORSMiddleware` allows `http://localhost:3000` and `http://127.0.0.1:3000` via `CORS_ORIGINS` env var
- [x] Redis graceful fallback — `_init_redis()` in `api/main.py` tries real Redis, falls back to `MockRedisService` on failure with a warning log
- [ ] Smoke-test: start backend + frontend, confirm data flows to Dashboard and Race Results pages (requires manual run)

---

## Phase 2 — Real Auth ✅

**Goal:** Secure, backend-issued sessions instead of browser-only auth.

- [x] Add JWT auth to FastAPI (`python-jose` + `passlib`)
  - `POST /auth/signup` — create user, hash password, return token
  - `POST /auth/login` — verify credentials, return token
  - `GET /auth/me` — return current user from token
  - `PATCH /auth/me/preferences` — update preferences
- [x] Store users in DuckDB (new `users` table: id, username, email, hashed_password, preferences, created_at)
- [x] Update `AuthContext.tsx` to call the backend instead of IndexedDB/localStorage
- [x] Store JWT in `localStorage` (simpler than httpOnly cookie; no CSRF needed; XSS risk acceptable at this stage)
- [x] `get_current_user` Depends guard added; wired to `/auth/me` and `/auth/me/preferences`
- [ ] Remove `bcryptjs` dependency from the frontend (deferred to Phase 7 cleanup)

---

## Phase 3 — Data Layer ✅

**Goal:** Real F1 historical data flowing through the app.

- [x] Ingest 2024 season into DuckDB via `ingest/simple_ingest.py` — confirmed: 29 drivers, 25 races, 479 race results (lap telemetry not included in fast ingest)
- [x] Fixed DuckDB `store_*` bug — all 5 methods used `execute(..., {"df": df})` which DuckDB silently rejected; rewrote with `executemany()` + positional `?` params; also fixed composite PKs (`race_results` on `(race_id, position)`, `laps` on `(race_id, driver_id, lap_number)`) replacing broken auto-increment `id` columns
- [x] Fixed data source routing: added 2024 to `FASTF1_YEARS`; switched Ergast → Jolpica (ergast.com shut down 2024); fixed `round_number` → `round` field name bug in ergast_service.py
- [x] Race Results page → `/race/{race_id}/results` — working with real data
- [x] Driver Analytics → `/api/drivers`, `/api/constructors` — served via FastF1 fallback for 2020–2024
- [x] Track Analytics → `/api/races` — served via Jolpica for 2025+
- [ ] Lap Data page → `/race/{race_id}/laps` — empty until lap data is ingested (needs `session.load(laps=True)`); full telemetry (sector times, speed traces) is a future enhancement
- [x] Dashboard stats — already wired to `/api/drivers` + `/api/races`; derives leader, next race, favourite driver, and recent results from real data (earlier "hardcoded" note was stale)
- [ ] Incremental ingest for new races (deferred — run `simple_ingest.py` manually after each race weekend)

---

## Phase 4 — Live Data

**Goal:** Real-time race data working end-to-end.

- [ ] Confirm real Redis is running (via Docker or standalone) and remove mock fallback for production
- [x] Verify `live/poller.py` correctly pushes to Redis during a live session — `_update_live_state` now emits the canonical LiveState shape (`driver_id`, `lap`, `total_laps`, `track_status`); still needs a real session to verify end-to-end
- [x] Connect `LiveDataMonitor.tsx` to the backend WebSocket (`ws://localhost:8000/ws/live/{race_id}`) — already wired; fixed WS envelope so frontend receives flat `LiveState` in `msg.data`
- [x] Connect `LiveAnalytics.tsx` to live state — polls `/live/{race_id}/state` every 15s and renders positions when `session_status === "live"`
- [x] Add reconnect logic in the frontend WebSocket client (backoff + toast notification on disconnect) — exponential backoff + countdown already in `LiveDataMonitor.tsx`
- [x] Test full loop via automated tests: `tests/test_live.py` covers `_unwrap_live_state`, `/simulate/live`, `/live/{id}/state`, WS `/ws/live/{id}` initial-state flat delivery, and `/health` — 12 tests pass against the mock-Redis fallback
- [ ] End-to-end smoke test with the real poller during an F1 session (deferred — needs a live session)

**Implementation notes:**
- `api/main.py:_unwrap_live_state` flattens Redis envelopes (`{race_id, timestamp, state}` and `{race_id, timestamp, update: {type, state}}`) so WS and REST both return the inner `state` dict.
- `/simulate/live/{race_id}` and the poller emit the same canonical fields the frontend expects (`driver_id`, `lap`, `total_laps`, `track_status`, `positions[].status`, etc).

---

## Phase 5 — Predictions (IN PROGRESS)

**Goal:** A real race outcome prediction using historical F1 data.

- [x] Add `grid` (qualifying position) column to `race_results` table — strongest single predictor of finish position
- [x] Update `ingest/simple_ingest.py` to capture `GridPosition` from FastF1
- [ ] Re-ingest 2024 data to populate grid positions (existing rows have `grid = NULL`)
- [ ] Choose a prediction model (see options below)
- [ ] Build `api/services/prediction_service.py` — trains on DuckDB data, predicts finish order
- [ ] Add REST endpoints: `POST /predict/{race_id}`, `GET /predict/{race_id}`
- [ ] Wire up Predictions page in the frontend
- [ ] Add `scikit-learn` to `requirements.txt`

**Reference:** `2025_f1_predictions-main/` — GradientBoostingRegressor approach; adapted for our dynamic data pipeline (no hardcoded qualifying data)

---

## Phase 6 — Production Readiness ✅

**Goal:** Deployable, observable, and secure.

- [x] **Rate limiting** — `slowapi` wired up with `RATE_LIMIT` env var (default `60/minute` general, `10/minute` for `/auth/signup`, `/auth/login`, `/simulate/live`)
- [x] **Structured logging** — `LOG_FORMAT=json` activates JSON via `python-json-logger`; `LOG_LEVEL` env var controls level (default `INFO`); plain text in dev by default
- [x] **CI** — `.github/workflows/ci.yml`: runs `pytest tests/ -v` (Python 3.12) and `tsc --noEmit` (Node 20) on push to `main` and PRs
- [x] **Secrets audit** — only `JWT_SECRET` has a dev fallback; added startup warning when it's using the default value; no other hardcoded secrets found
- [x] **`/health` hardened** — independent probes for Redis (distinguishes real vs mock, pings `get_redis_info`) and DuckDB (runs `SELECT 1`); per-check try/except so one failure doesn't 500; overall `status` summarizes as `ok`/`degraded`/`error`; returns 503 only when DuckDB is unreachable. Covered by `tests/test_live.py::TestHealthEndpoint` (3 tests).
- [x] **Navbar unification (UX prod-readiness)** — merged `PublicHeader` + `Navigation` into a single `Navigation` component; all nav items always visible; auth-gated items (`Dashboard`, `Live Data`, `Race Results`, `Lap Data`, `Live Monitor`, `Data Manager`) show a lock badge when signed out and redirect to `/login` with `state:{from,fromLabel}`; `LoginPage` shows a "sign-in required for X" banner and returns to `from` after login; `App.tsx` uses `RequireAuth` / `RedirectIfAuthed` guards so URL-typers are handled the same way; mobile hamburger menu; unified h-16 height/logo

---

## Hosting — Free Stack

All services below have free tiers with no credit card required (or a one-time free credit).

| Service | What it hosts | Free tier limits |
|---------|--------------|-----------------|
| **Vercel** | React frontend | Unlimited personal projects, custom domain |
| **Fly.io** | FastAPI backend | 3 free shared VMs, no spin-down, persistent volumes (good for DuckDB), WebSocket support |
| **Supabase** | PostgreSQL (users, auth) | 500 MB DB, 2 projects free |
| **Upstash** | Redis (live race state) | 10,000 commands/day free — enough for race weekends |
| **GitHub** | DuckDB historical data | Store the populated `.duckdb` file on a Fly.io persistent volume — survives restarts without Git LFS |

### Why this stack

- **Fly.io builds remotely** — use `flyctl deploy --remote-only` so the container is built on Fly's servers, nothing runs on your local machine
- **DuckDB stays** — don't migrate to PostgreSQL. Use Supabase Postgres only for user accounts/auth. Keep DuckDB for all F1 analytics queries (it's faster for that anyway)
- **Upstash Redis** is serverless — no always-on process, billed per command, perfect for a poller that only runs on race weekends

### Architecture in production

```
Browser
  │
  ├── React app (Vercel CDN)
  │
  └── FastAPI (Render)
        ├── Auth → Supabase Postgres (users table)
        ├── F1 data → DuckDB file (bundled or fetched from Git LFS on startup)
        ├── Live state → Upstash Redis
        └── WebSocket → same Render service (Render supports WS on free tier)
```

### Deploy steps (to add in Phase 6)
- [ ] Run `flyctl launch` in repo root — generates `fly.toml` (defines app name, region, VM size)
- [ ] Create a Fly persistent volume for DuckDB: `flyctl volumes create f1_data --size 1`
- [ ] Mount the volume at `/app/data` in `fly.toml` so the DuckDB file survives deploys
- [ ] Add Vercel config (`vercel.json`) — set `REACT_APP_API_URL` to the Fly app URL (`https://<app>.fly.dev`)
- [ ] Set secrets on Fly: `flyctl secrets set JWT_SECRET=... SUPABASE_DATABASE_URL=... REDIS_URL=...`
- [ ] Add a `POST_DEPLOY_INGEST=true` flag: on first boot, run `ingest/historical_ingest.py` if DuckDB file is absent
- [ ] Set up auto-deploy from `main` branch via GitHub Actions (`flyctl deploy --remote-only` step) — all builds happen on Fly's servers, not locally

### Trade-offs to know
- Fly.io free tier **does not sleep** — no cold start problem
- Fly free tier includes 3 shared VMs (256 MB RAM each) and 3 GB persistent storage — enough for this project
- Upstash free tier (10K commands/day) is enough for race weekends but would hit limits if you polled every second all day — the poller's 5s default interval is fine
- Supabase free projects **pause after 1 week of inactivity** — restore is one click but worth knowing

---

## Phase 7 — Cleanup

**Goal:** Remove dead code and files once all phases are complete and verified working.

- [ ] Delete `backend/` — older, less complete duplicate of `api/`; `api/main.py` is the live app
- [ ] Delete `api/simple_main.py` — no-Redis stub used for early testing, now dead
- [ ] Delete `api/enhanced_main.py` — iterative dev file; its features were merged into `api/main.py`
- [ ] Delete `api/working_enhanced_main.py` — same, another iterative scratch file
- [ ] Delete `api/start.py` if present — superseded by `start_backend.py` at repo root
- [ ] Delete `demo_enhanced_features.py` — one-off demo script, not part of the app
- [ ] Delete `test_websocket.py` — ad-hoc script, proper tests live in `tests/`
- [ ] Remove `build/` from git tracking (`git rm -r --cached build/`) — already in `.gitignore` but was committed
- [ ] Update `.gitignore` to cover: `__pycache__/`, `*.pyc`, `.venv/`, `venv/`, `api/cache/`, `api/fastf1_cache/`, `data/fastf1_cache/`
- [ ] Remove `bcryptjs` frontend dependency (auth moved fully to backend JWT)

---

## Future Enhancements

Features that are intentionally deferred — not in scope for the current build but worth revisiting once the core is stable and deployed.

### Data & Analytics
- **Lap telemetry** — sector times, speed traces, tyre degradation curves; needs `historical_ingest.py` (hours-long FastF1 download per season)
- **Live timing detail** — sector splits, mini-sectors, DRS/pit status per driver during a live session
- **Constructor championship tracker** — points progression chart across the season
- **Head-to-head driver comparison** — side-by-side lap time distributions for any two drivers at the same circuit

### Predictions
- **Real ML model** — XGBoost/LightGBM trained on qualifying position + constructor form + track history; currently a stub in `predict/worker.py`
- **Confidence intervals** — show prediction uncertainty, not just a single finish order
- **Post-race model evaluation** — compare predicted vs actual finish, log accuracy over time

### Infrastructure
- **Real Redis in production** — swap MockRedisService for Upstash; remove mock fallback from prod config
- **Incremental ingest automation** — trigger `incremental_ingest.py` automatically after each race weekend via a scheduled job or GitHub Action
- **Redis Cluster / horizontal scaling** — only relevant if the platform grows beyond a single Fly.io VM

### UX / Frontend
- **Lap Data page** — populate from ingested lap rows; requires laps ingest (`session.load(laps=True)`)
- **Push notifications** — notify users when a live session starts or when a safety car is deployed
- **Multi-language support** — i18n for non-English markets
- **Mobile app** — React Native or PWA wrapper

### Platform
- **API versioning** — `/v1/` prefix once the API surface stabilises and external consumers exist
- **Paid hosting / custom domain** — revisit if the platform gets real users
- **User-facing predictions UI** — dedicated Predictions page or Dashboard widget once the model is real

---

## Out of Scope (for now)
- Everything listed under Future Enhancements above — deliberately deferred, not forgotten
