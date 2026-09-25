"""Put the right names on stored drivers (see api/services/driver_names.py for the sources).

    python scripts/sync_driver_names.py --dry-run    # list the changes
    python scripts/sync_driver_names.py

Everyone with stored results who raced gets Jolpica's name (so "Andrea Kimi Antonelli" matches the
standings); a driver whose stored name is blank, "None None" or another driver's (an FP1 stand-in)
gets OpenF1's, or just the three-letter code when OpenF1 doesn't know them either — a wrong name is
worse than none. Drivers with no stored results at all are left alone. Uses DATABASE_URL (Supabase),
or the local DuckDB when it isn't set.
"""
import argparse
import asyncio
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "api"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

import httpx  # noqa: E402

from services.driver_names import jolpica_names, openf1_name, same_name  # noqa: E402

PLACEHOLDERS = {"", "None None", None}


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
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    db = await open_db()
    try:
        drivers = {d["driver_id"]: d for d in await db.get_all_drivers()}
        rows = await db._run_query("""
            SELECT DISTINCT rr.driver_id, r.year FROM race_results rr JOIN races r ON rr.race_id = r.race_id
        """)
        years_by_driver = {}
        for r in rows:
            years_by_driver.setdefault(r["driver_id"], set()).add(int(r["year"]))

        with httpx.Client(timeout=20) as client:
            official = {}
            for year in sorted({y for ys in years_by_driver.values() for y in ys}):
                official.update(jolpica_names(year, client))   # later seasons win

            name_counts = Counter(d.get("full_name") for code, d in drivers.items() if code in years_by_driver)
            changes = []
            for code in sorted(years_by_driver):
                current = drivers.get(code, {}).get("full_name")
                new = official.get(code.upper())
                # Another driver's name: it's the official name of a different code.
                borrowed = any(same_name(current, name) for c, name in official.items() if c != code.upper())
                if not new and (current in PLACEHOLDERS or name_counts[current] > 1 or borrowed):
                    # A wrong name is worse than none: fall back to the code itself.
                    new = openf1_name(code, client) or (code.upper() if borrowed or current in PLACEHOLDERS else None)
                if new and new != current:
                    changes.append((code, current, new))

        for code, old, new in changes:
            print(f"{code:4} {old!s:24} -> {new}")
        print(f"{len(changes)} change(s)")
        if changes and not args.dry_run:
            await db.store_drivers([{**drivers.get(code, {"driver_id": code}), "driver_id": code, "full_name": new}
                                    for code, _, new in changes], rename=True)
            print("stored")
    finally:
        await db.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
