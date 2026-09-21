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

## Pending (added 2026-09-21, from the data audit + health poller work)

### Data correctness
- [ ] **Stale duplicate row** — `2026_British` sprint has Albon twice: real P18 row and a leftover P99 row (NaN points, from the first ingest). Delete the P99 row (Supabase `race_results`, `session_type='sprint'`)
- [ ] **Upsert leaves stale rows** — `store_race_results` upserts on `(race_id, session_type, position)`, so a re-ingest never removes rows at positions no longer used. Delete-then-insert per `(race_id, session_type)` in `supabase_f1_service.py` and `simple_duckdb_service.py`
- [ ] **Podiums always 0 on the Drivers tab** — hard-coded at `api/services/ergast_service.py:115`; 23/23 drivers show 0 (even ones with wins). Compute from stored race results (position ≤ 3)
- [ ] **Post-race penalties change results after ingest** (found: 2026 Monaco, Gasly P3 → P7, fixed by re-ingest). Consider a scheduled re-ingest of the last few rounds so later stewards' decisions are picked up
- [ ] **Qualifying disagrees with Jolpica** for 2026 Canada (r5, P14–P16) and Belgium (r10, P4–P10). Rows were fetched fresh from FastF1, so it's a source disagreement, not staleness — decide which source is authoritative
- [ ] **Naming inconsistency** — DB has "Kimi Antonelli", standings have "Andrea Kimi Antonelli"
- [ ] **Unclassified drivers stored at position 99** — 2022 Saudi (Schumacher), 2023 Singapore (Stroll), 2023 Azerbaijan sprint (Sargeant); official classification ranks them last instead
- [ ] **Verify 2026 round 16** — Jolpica calls it "Bahrain Grand Prix in Malaysia" (location "Kuala Lumpur"), the backend shows "Bahrain Grand Prix". Confirm the name/venue, then add its length, corners and lap record to `src/data/trackFacts.ts` (currently shows "—")
- [ ] **Static snapshots in `public/data/`** are now only used for finished seasons (guard in `backendApi.fetchStatic`). The 2026 files there are stale (Apr 16: 22-round calendar, standings after round 3) — regenerate with `scripts/generate_static_data.py` or delete the current-season files so they can't mislead
- [ ] **Podiums** are hidden on the Drivers tab until the source provides them (see the podiums item above) — restore the column once fixed
- [ ] 2020–2021 are not in Supabase (2022–2026 only); qualifying for 2022–2025 is only loaded lazily on demand

### Not yet verified
- [ ] Lap Data page data for recent races, Tracks tab, and on-screen check of every page after the data fixes
- [ ] Live page shows "no data" until the next session (Azerbaijan, 2026-09-26) — expected; real-session smoke test still open (Phase 4)

### Deployment (Render + Supabase + Upstash) — verify after the first deploy
- [ ] **Set `SUPABASE_ACCESS_TOKEN` in the Render dashboard** (Supabase → Account → Access Tokens). Without it a paused project can't be woken automatically — the API just keeps retrying and the site shows "waking up the database" until someone restores it by hand
- [ ] Confirm `REACT_APP_API_URL` is set on the static site (it is baked in at build time) and `CORS_ORIGINS` on the API includes the frontend URL
- [ ] Not tested here: the real Supabase Management API restore call (only against a fake, though the endpoint/statuses match Supabase's published OpenAPI spec), the Docker image build (Docker Desktop wasn't running; dependency pins match the tested environment), and Render's actual cold start. After deploying, pause the project from the Supabase dashboard, open the site, and watch it recover
- [ ] Upstash free tier is 10K commands/day: each page load makes one `/health` call (a Redis `INFO`), and `LiveAnalytics` polls live state every 15s while open — keep an eye on usage
- [ ] `tests/test_api.py` imports a module that no longer exists (`api.services.duckdb_service`), and `test_live.py::test_health_reports_redis_kind_and_probes_duckdb` assumes mock Redis but `.env` gives the tests real Upstash — both predate this work
- [ ] Add a `.dockerignore` (venv/, node_modules/, data/ are ~2 GB of build context)

### Tooling
- [ ] Health poller's Supabase restore path is only tested against a fake API — needs `SUPABASE_ACCESS_TOKEN` to exercise it for real (`scripts/health_poller.py`)
- [ ] Uncommitted work: `laps_completed` ingest + Race Results table columns, health poller (`scripts/health_poller.py`, `npm run up`, `.claude/launch.json`), `logs/` gitignore, CLAUDE.md notes. `cache/race_schedule_*.json` changes look like noise. Commit when approved (no push until then)

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
