"""Fill in missing FP1-FP3 results, one session at a time, retrying FastF1's flaky timing API.

`POST /admin/ingest` with `practice: true` re-fetches every session of every weekend and gives up on
a practice session after one failure ("Failed to load timing data"), which left 2022, 2025 and 2026
patchy. This only fetches the practice sessions a raced weekend is missing (a sprint weekend has
FP1 only) and retries each a few times with a growing pause.

    python scripts/backfill_practice.py --years 2022 2025 2026 --dry-run   # list what's missing
    python scripts/backfill_practice.py --years 2022 2025 2026

Writes to the database in DATABASE_URL (Supabase), or the local DuckDB when it isn't set. Retrain
and re-run the walk-forward backtest afterwards (POST /predict/train, POST /predict/backtest/refresh).
"""
import argparse
import asyncio
import logging
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "api"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from services import ingest_service  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logging.getLogger("fastf1").setLevel(logging.WARNING)
log = logging.getLogger("backfill")

FP_SESSION = {"fp1": "FP1", "fp2": "FP2", "fp3": "FP3"}
RETRY_PAUSES = (20, 60, 180)  # seconds before the 2nd, 3rd and 4th attempt


def expected_practice(is_sprint_weekend: bool) -> list:
    return ["fp1"] if is_sprint_weekend else ["fp1", "fp2", "fp3"]


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


async def missing_sessions(db, years):
    """(year, round, gp, [session types]) for every raced weekend missing practice."""
    todo = []
    for year in years:
        for race in await db.get_races_by_year(year):
            rows = await db._run_query(
                "SELECT DISTINCT session_type FROM race_results WHERE race_id = " + ("$1" if os.getenv("DATABASE_URL") else "?"),
                (race["race_id"],),
            )
            have = {r["session_type"] for r in rows}
            if "race" not in have:
                continue  # not raced yet
            missing = [s for s in expected_practice("sprint" in have) if s not in have]
            if missing:
                todo.append((year, int(race["round"]), race["gp"], missing))
    return todo


async def fetch_with_retries(db, year, round_n, session):
    for attempt in range(len(RETRY_PAUSES) + 1):
        try:
            result = await ingest_service.ingest_single_race(db, year, round_n, include_laps=False, session=session)
            if result.get("stored"):
                return result
            reason = result.get("reason", "nothing stored")
        except Exception as exc:
            reason = str(exc)
        if attempt < len(RETRY_PAUSES):
            log.info("  %s failed (%s) — retrying in %ss", session, reason[:80], RETRY_PAUSES[attempt])
            await asyncio.sleep(RETRY_PAUSES[attempt])
    log.warning("  %s gave up: %s", session, reason[:120])
    return None


async def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--years", type=int, nargs="+", required=True)
    parser.add_argument("--dry-run", action="store_true", help="only list the missing sessions")
    args = parser.parse_args()

    import fastf1
    cache_dir = os.getenv("FASTF1_CACHE_DIR", "data/fastf1_cache")
    os.makedirs(cache_dir, exist_ok=True)
    fastf1.Cache.enable_cache(cache_dir)

    db = await open_db()
    try:
        todo = await missing_sessions(db, args.years)
        total = sum(len(m) for *_, m in todo)
        log.info("%d weekends, %d practice sessions missing", len(todo), total)
        for year, round_n, gp, missing in todo:
            log.info("%s R%02d %s: %s", year, round_n, gp, ", ".join(missing))
        if args.dry_run:
            return

        done = failed = 0
        started = time.time()
        for year, round_n, gp, missing in todo:
            for session_type in missing:
                log.info("%s R%02d %s %s", year, round_n, gp, FP_SESSION[session_type])
                if await fetch_with_retries(db, year, round_n, FP_SESSION[session_type]):
                    done += 1
                else:
                    failed += 1
        log.info("Stored %d of %d sessions (%d failed) in %.0f min", done, total, failed, (time.time() - started) / 60)
    finally:
        await db.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
