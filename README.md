# Shif1 UP

**Formula 1 standings, results and predictions: all in one place, no account needed.**

🔗 **Live site: [shif1-up-1.onrender.com](https://shif1-up-1.onrender.com)**

> It runs on free hosting, so the first visit after a quiet spell can take up to a minute while the server and database wake up. A progress screen shows while that happens.

---

## What you can do

### 📊 Dashboard
- **Standings**: the drivers' championship for every season since 1950, and the constructors' since it began in 1958.
- **Wins and podiums**: turn on optional columns for race wins, race podiums, sprint wins and sprint podiums, per driver and per team.
- **Race results**: full classifications for races, sprints, qualifying and practice.
- **Tracks**: circuit facts and lap records.

### 🏆 Title Race
Who wins the championship?
- **Who can still win**, worked out exactly from the points still available and the tie-break rules.
- **The title-clinch picture**: whether it's already decided, and what margin the leader needs at the next race to seal it.
- **Each contender's chance**, from 10,000 simulated finishes to the season driven by the race model: title probability, projected points and the likeliest final position.
- **A track record**: the page shows how these projections would have done on past seasons.

### 🔮 Predictions
- **Qualifying and race order** for upcoming Grands Prix, from machine-learning models trained on results since 2022.
- **Win, pole and podium chances** next to each prediction, and an average finishing position.
- **Predicted vs Actual**: every prediction for past races, compared with what really happened.

### 📡 Live timing (on hold)
A live timing board is built: positions, gaps, sector times, tyres, pit stops and flags. It needs a paid live-data feed, so on the public site the Live pages show "coming soon". Admins can play back any finished session through the same board.

---

## How good are the predictions?

These figures are measured honestly. Each season is predicted by a model that has only seen *earlier* seasons, and never the results it's being tested on.

| | Result (2023 – 2026, 84 races) |
|---|---|
| Qualifying order | off by **~4 places** per driver on average |
| Race order | off by **~3.5 places** per driver on average |
| Title Race, drivers' champion named correctly | 73% of checkpoints (backing the current leader: 74%) |
| Title Race, constructors' champion named correctly | 76% of checkpoints (backing the current leader: 73%) |

F1 is unpredictable (crashes, strategy, weather), and the numbers reflect that. Some things were tried and **left out** because they didn't measurably help: weather, circuit type, and teammate comparisons.

---

## Built with

| Layer | Technology |
|---|---|
| Frontend | React, TypeScript, Tailwind CSS, Chart.js, Framer Motion |
| Backend | FastAPI (Python) |
| Database | PostgreSQL on Supabase (DuckDB locally) |
| Live state | Redis (Upstash) with WebSockets |
| Machine learning | LightGBM ranking models, plus a calibrated race simulation for the odds |
| Data sources | [FastF1](https://github.com/theOehrly/Fast-F1), [Jolpica-F1](https://github.com/jolpica/jolpica-f1) (the Ergast successor), [OpenF1](https://openf1.org) |
| Hosting | [Render](https://render.com) (API + static site) |

```
Browser ──► React app (static site)
               │
               ▼
           FastAPI ──► PostgreSQL (results, standings, predictions cache)
               │   ──► Redis (live timing state + pub/sub → WebSocket)
               │   ──► LightGBM models (trained on start-up)
               ▼
   FastF1 · Jolpica · OpenF1   (race data)
```

---

## Running it locally

**You'll need** Python 3.12 and Node.js 18 or newer.

```bash
git clone https://github.com/knightmare-26/shif1_up.git
cd shif1_up

# Backend dependencies
python -m venv venv
venv\Scripts\activate              # macOS/Linux: source venv/bin/activate
pip install -r api/requirements.txt

# Frontend dependencies
npm install

# Start both (API on :8000, site on :3000)
npm run dev
```

With no configuration, it uses the bundled DuckDB database (`data/f1_history.duckdb`) and an in-memory stand-in for Redis. Sign-in is switched off in that mode. To use your own services, create a `.env` file:

| Variable | What it's for |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string (e.g. Supabase) |
| `REDIS_URL` | Redis connection string |
| `JWT_SECRET` | Signs login tokens |
| `REACT_APP_API_URL` | Where the frontend finds the API (default `http://localhost:8000`) |

API docs are at `http://localhost:8000/docs` once it's running.

**Tests**
```bash
venv\Scripts\python -m pytest tests --ignore=tests/test_api.py   # backend
npx react-scripts test --watchAll=false src/components           # frontend
```
The test suite never touches real services: it runs on an in-memory Redis and a throwaway local database.

**Loading data**
```bash
python ingest/simple_ingest.py --years 2025 2026                  # results and standings
python scripts/backfill_practice.py --years 2026 --dry-run        # missing practice sessions
```

---

## Project layout

```
api/            FastAPI app
  main.py         endpoints
  services/       database, predictions, title-race simulation, ingest, live timing
ingest/         scripts to load historical seasons
live/           standalone FastF1 poller (local use)
scripts/        maintenance: practice backfill, driver names, static data, health poller
src/            React frontend (components, UI kit, API client)
public/data/    pre-built JSON for finished seasons (served straight from the CDN)
tests/          backend tests
render.yaml     Render deployment
```

Detailed developer notes, covering architecture decisions, data quirks and how each part works, are in [CLAUDE.md](CLAUDE.md).

---

## Acknowledgements

Shif1 UP is built on community F1 data:
- [FastF1](https://github.com/theOehrly/Fast-F1)
- [Jolpica-F1](https://github.com/jolpica/jolpica-f1)
- [OpenF1](https://openf1.org)

Thank you to their maintainers.

*Shif1 UP is an unofficial fan project. It isn't associated with Formula 1 or any of its companies. F1, Formula One, Grand Prix and related marks are trademarks of Formula One Licensing B.V.*
