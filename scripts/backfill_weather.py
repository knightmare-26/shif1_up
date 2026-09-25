"""Store every finished session's weather (2023 onwards) in the database, so the Race Results
weather panel never has to wait for OpenF1 — which also shuts free access while any F1 session is
live. Sessions already stored are skipped; run it again any time to pick up new ones.

    python scripts/backfill_weather.py                 # 2023 to this season
    python scripts/backfill_weather.py --years 2026

Uses DATABASE_URL (Supabase), or the local DuckDB when it isn't set.
"""
import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "api"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from services.openf1_live import CODE_FOR_NAME, OpenF1Client, OpenF1Locked, parse_time  # noqa: E402
from services.session_replay import FIRST_OPENF1_SEASON, SessionReplayService, session_key  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("weather")
LOCK_WAIT_SECONDS = 600


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


async def unlocked(call):
    """Run an OpenF1 call, waiting out any live-session lock."""
    while True:
        try:
            return await call()
        except OpenF1Locked:
            log.info("OpenF1 is locked while a session is live — waiting %d min", LOCK_WAIT_SECONDS // 60)
            await asyncio.sleep(LOCK_WAIT_SECONDS)


async def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--years", type=int, nargs="+",
                        default=list(range(FIRST_OPENF1_SEASON, datetime.now().year + 1)))
    args = parser.parse_args()

    db = await open_db()
    client = OpenF1Client(creds={})
    service = SessionReplayService(lambda: db, client_factory=lambda: client)
    stored = skipped = empty = 0
    try:
        now = datetime.now(timezone.utc)
        for year in args.years:
            meetings = await unlocked(lambda: client.get("meetings", year=year))
            for meeting in meetings:
                sessions = await unlocked(lambda: client.get("sessions", meeting_key=meeting["meeting_key"]))
                for session in sessions:
                    code = CODE_FOR_NAME.get(session.get("session_name"))
                    end = parse_time(session.get("date_end"))
                    if not code or session.get("is_cancelled") or end is None or end > now:
                        continue
                    name = meeting.get("meeting_name", "")
                    key = session_key(year, name, code)
                    if await service._stored_weather(key):
                        skipped += 1
                        continue
                    service._sessions[key] = {**session, "meeting_name": name}   # no second lookup
                    _, readings = await unlocked(lambda: service.load_weather(year, name, code))
                    if readings:
                        stored += 1
                        log.info("%s %s %s: %d readings", year, name, code, len(readings))
                    else:
                        empty += 1
        log.info("Stored %d sessions, %d already stored, %d without weather data", stored, skipped, empty)
    finally:
        await client.close()
        await db.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
