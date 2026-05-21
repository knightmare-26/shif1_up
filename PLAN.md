# Shif1 UP — Build Plan

## Current State (as of 2026-05-21)

### What's working
- React/TypeScript frontend deployed as Render Static Site
- FastAPI backend deployed as Render Docker Web Service
- Dashboard with sub-tabs: Overview, Drivers, Teams, Tracks
- Navigation: Home, Dashboard, Predictions, Race Results, Live, Data Manager
- Race Predictions page — ML-powered qualifying + race finish predictions
- Upstash Redis for live race WebSocket streaming
- Supabase PostgreSQL — users/auth + `SupabaseF1Service` built and wired for F1 data
- Live Data Monitor with WebSocket reconnect + exponential backoff
- UI fully sanitized — no API names, timestamps, or infra details visible to users
- Auth code present but content not gated; sign-up/sign-in CTA removed from home page

### Remaining gaps
1. **Supabase F1 ingest not run yet** — verify `DATABASE_URL` on Render uses direct port 5432 (not pooler 6543), then trigger ingest via Data Manager
2. **Grid data missing until ingest runs** — predictions show warning; fixed once 2022–2024 ingest completes
3. **Live end-to-end smoke test** — needs a real F1 session; mocked via `/simulate/live`

---

## Phase 1 — Stabilize the Foundation ✅

- [x] Single FastAPI app (`api/main:app`) — `backend/` dir is dead code
- [x] `backendApi.ts` URL mismatches fixed
- [x] CORS configured via `CORS_ORIGINS` env var
- [x] Redis graceful fallback — real Redis → `MockRedisService`

---

## Phase 2 — Auth ✅ (shelved in UI, code retained)

- [x] JWT auth — `POST /auth/signup`, `POST /auth/login`, `GET /auth/me`
- [x] Users stored in Supabase PostgreSQL (`users` table via `PostgresService`)
- [x] `AuthContext.tsx` calls backend; JWT in localStorage
- [x] `AuthProvider` wraps app shell (required — components call `useAuth()`)
- [x] Auth routes exist; content not gated (shelved by decision)
- [x] Sign-up/sign-in CTA removed from home page

---

## Phase 3 — Data Layer ✅

- [x] Ingest 2024 season via `ingest/simple_ingest.py`
- [x] Fixed DuckDB `store_*` bugs (`executemany()` + positional params)
- [x] Data source routing: FastF1 for 2020–2024, Jolpica-Ergast for others
- [x] Race Results, Driver Analytics, Track Analytics on real data
- [ ] Lap Data — empty until lap telemetry is ingested (`--laps` flag on ingest)

---

## Phase 4 — Live Data ✅ (pending real-session smoke test)

- [x] `live/poller.py` emits canonical `LiveState` to Redis
- [x] WS `/ws/live/{race_id}` delivers flat `LiveState` (envelope unwrapped server-side)
- [x] `LiveDataMonitor.tsx` — WebSocket connect/reconnect with exponential backoff
- [x] `LiveAnalytics.tsx` — polls live state every 15s, renders positions when live
- [x] `/simulate/live/{race_id}` for testing without a real session
- [ ] End-to-end smoke test during a real F1 session

---

## Phase 5 — Predictions ✅

- [x] `grid` column added to `race_results` (qualifying position — strongest predictor)
- [x] `prediction_service.py` — XGBoost (qualifying) + LightGBM (race finish)
- [x] `GET /predict/qualifying/{circuit}`, `GET /predict/race/{circuit}`
- [x] `GET /predict/status`, `GET /predict/circuits`, `POST /predict/train`
- [x] `Predictions.tsx` — circuit selector, side-by-side quali/race tables, retrain button
- [x] Model names hidden from UI

---

## Phase 6 — Production Readiness ✅

- [x] Rate limiting — `slowapi` (60/min general, 10/min auth endpoints)
- [x] Structured logging — `LOG_FORMAT=json`, `LOG_LEVEL` env vars
- [x] Secrets audit — only `JWT_SECRET` has dev fallback (logs warning)
- [x] `/health` hardened — independent Redis + DuckDB probes
- [x] CI shelved — `.github/workflows/ci.yml` deleted
- [x] Navbar simplified; Dashboard sub-tabs; Drivers/Tracks removed from top nav
- [x] UI sanitized — no API names, data sources, or infra details visible
- [x] Backend on Render Docker Web Service; frontend on Render Static Site
- [x] `public/_redirects` for React Router SPA routing on Render
- [x] `CLAUDE.local.md` gitignored for secrets; `CLAUDE.md` + `PLAN.md` updated

---

## Hosting — Current Stack

| Service | What it hosts | Notes |
|---------|--------------|-------|
| **Render** (Docker) | FastAPI backend | `env: docker`; `api/requirements.txt` |
| **Render** (Static Site) | React frontend | Auto-builds on push; `public/_redirects` |
| **Supabase** | PostgreSQL | Users/auth + F1 historical data (migration wired) |
| **Upstash** | Redis | Live race WebSocket state; 10K cmds/day free |

### Architecture

```
Browser
  │
  ├── React app (Render Static Site — CDN)
  │
  └── FastAPI (Render Docker Web Service)
        ├── Auth + F1 data → Supabase PostgreSQL
        ├── Live state     → Upstash Redis
        └── WebSocket      → same Render service
```

---

## Phase 7 — F1 Data Migration to Supabase (in progress)

- [x] `api/services/supabase_f1_service.py` — drop-in for `SimpleDuckDBService`
- [x] `api/main.py` — uses `SupabaseF1Service` when `DATABASE_URL` set; graceful startup on failure
- [x] `ingest/simple_ingest.py` — targets Supabase when `DATABASE_URL` set
- [x] `supabase/schema.sql` — reference schema
- [ ] Verify `DATABASE_URL` on Render uses direct connection (port 5432, not pooler 6543)
- [ ] Run ingest: 2022, 2023, 2024 seasons via Data Manager page
- [ ] Confirm predictions work and grid warning disappears
- [ ] Remove bundled DuckDB file from Docker image

---

## Phase 8 — Cleanup

- [ ] Delete `backend/` directory — dead code, never deployed
- [ ] Delete `api/simple_main.py`, `api/enhanced_main.py`, `api/working_enhanced_main.py`
- [ ] Remove `venv/` from git tracking (`git rm -r --cached venv/`)
- [ ] Update `.gitignore` to cover `venv/`, `__pycache__/`, `data/fastf1_cache/`

---

## Future Enhancements

### Data & Analytics
- **Lap telemetry** — sector times, speed traces; needs `--laps` flag on ingest (hours-long download)
- **Live timing detail** — sector splits, DRS/pit status per driver during live sessions
- **Constructor championship tracker** — points progression chart across the season
- **Head-to-head driver comparison** — side-by-side lap time distributions

### Predictions
- **Confidence intervals** — show prediction uncertainty, not just a single finish order
- **Post-race model evaluation** — compare predicted vs actual, log accuracy over time
- **Tyre strategy integration** — use compound data as a prediction feature

### UX / Frontend
- **Lap Data page** — populate from ingested lap rows (blocked on telemetry ingest)
- **Push notifications** — notify when a live session starts or safety car is deployed
- **Mobile / PWA**

---

## Out of Scope (for now)
- Everything listed under Future Enhancements — deliberately deferred, not forgotten
