"""
Keep the data current while the API sleeps: the scheduled half of data upkeep.

Render's free server sleeps between visits, and everything that updates the data used to run only
inside it — so new results arrived when someone opened the site, often while OpenF1 was shut for a
live session (Singapore 2026's sprint and qualifying were missed that way). Run on GitHub's runners
by .github/workflows/data-upkeep.yml, this does one pass of exactly what the API's own loop does
(main._data_upkeep_pass: the weekend's sessions from OpenF1, or Jolpica while OpenF1 is shut;
preseason testing; data upkeep's gaps and fixes) — plus, with --results-refresh, the results refresh
(post-race penalties) — straight against Supabase. Render is never woken: the API reads the new data
the next time it starts (it retrains on every start), or at its next pass if it's awake (this leaves
a marker, main.UPKEEP_MARKER). Predicted vs Actual is rebuilt here, on a fast runner, rather than on
the API's 0.1 CPU when it next starts.

    DATABASE_URL=… python scripts/data_upkeep_job.py [--results-refresh]
    python scripts/data_upkeep_job.py --duckdb path/to/copy.duckdb      # a local dry run
"""
import argparse
import asyncio
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Optional

API = Path(__file__).resolve().parent.parent / "api"


async def run(results_refresh: bool = False, duckdb_path: Optional[str] = None) -> int:
    if str(API) not in sys.path:
        sys.path.insert(0, str(API))
    import main                                     # reads DATABASE_URL etc. from the environment

    if duckdb_path:
        from services.simple_duckdb_service import SimpleDuckDBService
        main.duckdb_service = SimpleDuckDBService(duckdb_path)
        await main.duckdb_service.initialize()
    elif not main.DATABASE_URL:
        print("::error::DATABASE_URL isn't set (a repository secret): nothing to update.")
        return 1
    else:
        await main._connect_database()
    try:
        changed, _ = await main._data_upkeep_pass()
        if results_refresh:
            refreshed = await main.ingest_service.refresh_recent_results(main.duckdb_service, main.RESULTS_REFRESH_DAYS)
            if refreshed:
                changed += [f"{s['race_id']} {s['session_type']} (corrected)" for s in refreshed]
                await main.prediction_service.train(main.duckdb_service)
        if changed:
            await main._mark_data_stored(changed)
        # Training starts the Predicted vs Actual rebuild in the background when it's missing
        # anything; this run waits for it (and starts it if the data changed without a retrain).
        await main._keep_backtest_current()
        if main._walkforward_job is not None:
            await main._walkforward_job
        print("Stored: " + (", ".join(changed) if changed else "nothing new"))
        return 0
    finally:
        if duckdb_path:
            main.duckdb_service = None
        else:
            await main._disconnect_database()


def cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--results-refresh", action="store_true", help="also re-fetch the last 14 days' results")
    parser.add_argument("--duckdb", help="run against a local DuckDB copy instead of Supabase (a dry run)")
    args = parser.parse_args()
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(levelname)s %(name)s: %(message)s")
    os.environ.setdefault("MODEL_DIR", tempfile.mkdtemp(prefix="models-"))
    os.environ.setdefault("CACHE_DIR", tempfile.mkdtemp(prefix="cache-"))
    return asyncio.run(run(args.results_refresh, args.duckdb))


if __name__ == "__main__":
    sys.exit(cli())
