"""Store each season's preseason testing summary (best lap per driver) for the predictions (#35).

    python scripts/backfill_testing.py --years 2022 2023 2024 2025 2026
    python scripts/backfill_testing.py --years 2026 --json testing.json     # write a file instead

OpenF1 from 2023 (free), FastF1 before that (slow; a test without public timing is skipped).
Writes to the database in DATABASE_URL (Supabase), or the local DuckDB when it isn't set. The API
stores the current season's testing by itself once it has run (the weekend loader).
"""
import argparse
import asyncio
import json
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "api"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from services import preseason_testing  # noqa: E402
from services.openf1_live import OpenF1Client  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logging.getLogger("fastf1").setLevel(logging.WARNING)
log = logging.getLogger("testing")
FIRST_OPENF1 = 2023


async def open_db():
    url = os.getenv("DATABASE_URL")
    if url:
        from services.supabase_f1_service import SupabaseF1Service
        db = SupabaseF1Service(url)
    else:
        from services.simple_duckdb_service import SimpleDuckDBService
        db = SimpleDuckDBService(os.getenv("DUCKDB_PATH", "data/f1_history.duckdb"))
    await db.initialize()
    return db


async def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--years", type=int, nargs="+", required=True)
    parser.add_argument("--json", help="write the summaries to this file instead of the database")
    args = parser.parse_args()

    import fastf1
    cache_dir = os.getenv("FASTF1_CACHE_DIR", "data/fastf1_cache")
    os.makedirs(cache_dir, exist_ok=True)
    fastf1.Cache.enable_cache(cache_dir)

    client = OpenF1Client(creds={})
    found = {}
    try:
        for year in args.years:
            if year >= FIRST_OPENF1:
                testing = await preseason_testing.from_openf1(client, year)
            else:
                testing = await asyncio.get_event_loop().run_in_executor(None, preseason_testing.from_fastf1, year)
            if not testing:
                log.warning("%s: no testing found", year)
                continue
            top = ", ".join(f"{d['driver_id']} {d['best_lap']:.3f}" for d in testing["drivers"][:3])
            log.info("%s: %d sessions, %d drivers (%s) — fastest %s", year, testing["sessions"],
                     len(testing["drivers"]), testing["source"], top)
            found[year] = testing
    finally:
        await client.close()

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(found, f, indent=1)
        log.info("wrote %s", args.json)
        return
    db = await open_db()
    try:
        for testing in found.values():
            await preseason_testing.store(db, testing)
        log.info("stored %d seasons", len(found))
    finally:
        await db.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
