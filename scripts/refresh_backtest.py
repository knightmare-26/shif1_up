"""Rebuild the walk-forward backtest (the Predictions page's Predicted vs Actual tab) and store it.

The API rebuilds it by itself once its models have been trained on new race results; this does
the same from a local machine — handy when the server is asleep or short on CPU.

    python scripts/refresh_backtest.py           # refits only what changed
    python scripts/refresh_backtest.py --full    # refits everything

Uses DATABASE_URL (Supabase), or the local DuckDB when it isn't set.
"""
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "api"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from services.prediction_service import PredictionService  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("backtest")


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
    db = await open_db()
    try:
        before = await db.get_prediction_cache("_walkforward", "v1")
        if before:
            log.info("stored: %d races (%s)", len(before["result"].get("races", [])), before["result"].get("data_fingerprint"))
        result = await PredictionService(model_dir="unused").walk_forward_backtest(
            db, years_back=3, previous=None if "--full" in sys.argv else (before or {}).get("result"))
        if not result.get("races"):
            log.error("no races scored: %s", result.get("error"))
            return 1
        await db.set_prediction_cache("_walkforward", "v1", result["data_fingerprint"], result)
        latest = result["races"][0]
        log.info("stored: %d races (%s, %d refits), latest %s round %s — %s", len(result["races"]),
                 result["data_fingerprint"], result.get("refits", 0), latest["year"], latest["round"], latest["race_name"])
        return 0
    finally:
        await db.cleanup()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
