"""
Keep the data current while the API sleeps: the scheduled half of data upkeep.

Render's free server sleeps between visits, and everything that updates the data used to run only
inside it — so new results arrived when someone opened the site, often while OpenF1 was shut for a
live session (Singapore 2026's sprint and qualifying were missed that way). Run on GitHub's runners
by .github/workflows/data-upkeep.yml, this does what the API's own loop does (main._data_upkeep_pass:
the weekend's sessions from OpenF1, or Jolpica while OpenF1 is shut; preseason testing; data upkeep's
gaps and fixes) — plus, with --results-refresh, the results refresh (post-race penalties) — straight
against Supabase. Render is never woken: the API reads the new data the next time it starts (it
retrains on every start), or at its next pass if it's awake (each pass that stores something leaves
a marker, main.UPKEEP_MARKER). Predicted vs Actual is rebuilt here, on a fast runner, rather than on
the API's 0.1 CPU when it next starts.

With --until (a race weekend, see scripts/upkeep_schedule.py) it stays on: a pass every 15 minutes
while a session's end is being watched, waiting in between.

    DATABASE_URL=… python scripts/data_upkeep_job.py [--results-refresh] [--until 2026-10-24T23:00:00+00:00]
    python scripts/data_upkeep_job.py --duckdb path/to/copy.duckdb      # a local dry run
"""
import argparse
import asyncio
import logging
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
API = HERE.parent / "api"
EVERY = timedelta(minutes=15)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


async def one_pass(main, results_refresh: bool = False) -> List[str]:
    """Store what's new, retrain on it, mark it for the API and rebuild Predicted vs Actual."""
    changed, _ = await main._data_upkeep_pass()
    if results_refresh:
        refreshed = await main.ingest_service.refresh_recent_results(main.duckdb_service, main.RESULTS_REFRESH_DAYS)
        if refreshed:
            changed += [f"{s['race_id']} {s['session_type']} (corrected)" for s in refreshed]
            await main.prediction_service.train(main.duckdb_service)
    if changed:
        stored_at = await main._mark_data_stored(changed)
        # These models already include it: the marker is for the API, not for the next pass here.
        main.prediction_service.data_read_at = max(main.prediction_service.data_read_at or "", stored_at)
    # Training starts the Predicted vs Actual rebuild in the background when it's missing anything;
    # wait for it (and start it if the data changed without a retrain).
    await main._keep_backtest_current()
    if main._walkforward_job is not None:
        await main._walkforward_job
    print(f"{_now():%H:%M} UTC stored: " + (", ".join(changed) if changed else "nothing new"), flush=True)
    return changed


async def run(results_refresh: bool = False, duckdb_path: Optional[str] = None,
              until: Optional[datetime] = None, calendar: Optional[List[Dict[str, Any]]] = None) -> int:
    for path in (str(API), str(HERE)):
        if path not in sys.path:
            sys.path.insert(0, path)
    import main                                     # reads DATABASE_URL etc. from the environment
    import upkeep_schedule

    if duckdb_path:
        from services.simple_duckdb_service import SimpleDuckDBService
        main.duckdb_service = SimpleDuckDBService(duckdb_path)
        await main.duckdb_service.initialize()
    elif not main.DATABASE_URL:
        print("::error::DATABASE_URL isn't set (a repository secret): nothing to update.")
        return 1
    else:
        await main._connect_database()
    # The site's cached predictions are the API's: it clears them when it retrains on new data.
    main.prediction_service.clear_cache_after_training = False
    try:
        await one_pass(main, results_refresh)
        if until:
            calendar = calendar if calendar is not None else (upkeep_schedule.fetch_calendar() or [])
            while _now() + EVERY < until:
                await _sleep(EVERY.total_seconds())
                session = upkeep_schedule.watching(_now(), calendar)
                if session:
                    print(f"{_now():%H:%M} UTC watching the end of {session}", flush=True)
                    await one_pass(main)
        return 0
    finally:
        if duckdb_path:
            main.duckdb_service = None
        else:
            await main._disconnect_database()


def cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--results-refresh", action="store_true", help="also re-fetch the last 14 days' results")
    parser.add_argument("--until", help="stay on until then (UTC ISO time), watching each session's end")
    parser.add_argument("--duckdb", help="run against a local DuckDB copy instead of Supabase (a dry run)")
    args = parser.parse_args()
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(levelname)s %(name)s: %(message)s")
    os.environ.setdefault("MODEL_DIR", tempfile.mkdtemp(prefix="models-"))
    os.environ.setdefault("CACHE_DIR", tempfile.mkdtemp(prefix="cache-"))
    until = datetime.fromisoformat(args.until) if args.until else None
    return asyncio.run(run(args.results_refresh, args.duckdb, until))


if __name__ == "__main__":
    sys.exit(cli())
