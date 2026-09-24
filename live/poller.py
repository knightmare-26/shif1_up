#!/usr/bin/env python3
"""
Live F1 Data Poller
Centralized process that polls FastF1 for live race data and publishes to Redis
"""

import asyncio
import argparse
import logging
import os
import sys
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import aiohttp
import pandas as pd
import fastf1
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.services.redis_service import RedisService

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")
INTERNAL_API_KEY = os.environ.get("INTERNAL_API_KEY", "")

# How many consecutive polls the lap count must stay flat, combined with a
# terminal result status, before a session is treated as finished. FastF1's
# live timing has known gaps, so this is a best-effort heuristic — the
# Data Manager admin override remains the fallback if it misses a race.
SESSION_END_STALL_POLLS = 3

# FastF1 session codes the poller can follow. R and S are classified (race
# position, lap counter); the rest are timed — ranked by best lap, with no
# meaningful lap counter or classification to wait for.
SESSIONS = ("FP1", "FP2", "FP3", "SQ", "S", "Q", "R")
TIMED_SESSIONS = frozenset({"FP1", "FP2", "FP3", "SQ", "Q"})

# Timed sessions have no leader "Status" to key the end off, so they end once
# no lap has been completed for this long — generous enough to ride out a red
# flag. Ingest is an idempotent upsert, so ending early can't lose data.
TIMED_SESSION_END_STALL_SECONDS = 300


def is_timed_session(session: str) -> bool:
    return session in TIMED_SESSIONS


def build_race_id(year: int, gp: str, session: str = "R") -> str:
    """Must match the frontend's id convention (LiveDataMonitor.tsx): spaces ->
    underscores, slashes -> hyphens. The race keeps the bare `{year}_{gp}` id
    (LiveAnalytics and existing clients rely on it); other sessions get a suffix."""
    base = f"{year}_{gp.replace(' ', '_').replace('/', '-')}"
    return base if session == "R" else f"{base}_{session}"


def _format_lap_time(td) -> Optional[str]:
    if td is None or pd.isna(td):
        return None
    total_ms = int(round(td.total_seconds() * 1000))
    minutes, rest = divmod(total_ms, 60_000)
    return f"{minutes}:{rest / 1000:06.3f}"


def build_timed_positions(laps: pd.DataFrame) -> List[Dict[str, Any]]:
    """Practice / qualifying table: drivers ordered by best lap so far. Drivers
    with no timed lap yet are listed last (status "No time") rather than dropped."""
    rows = []
    for driver, group in laps.groupby("Driver"):
        timed = group["LapTime"].dropna()
        last = group.sort_values("LapNumber").iloc[-1]
        rows.append({
            "driver": driver,
            "best": timed.min() if not timed.empty else None,
            "laps": int(group["LapNumber"].count()),
            "tyre": last.get("Compound"),
            "last": last.get("LapTime"),
        })

    rows.sort(key=lambda r: (r["best"] is None, r["best"] if r["best"] is not None else pd.Timedelta(0), r["driver"]))
    fastest = next((r["best"] for r in rows if r["best"] is not None), None)

    positions = []
    for index, r in enumerate(rows):
        gap = None
        if r["best"] is not None and fastest is not None and index > 0:
            gap = f"+{(r['best'] - fastest).total_seconds():.3f}"
        positions.append({
            "driver_id": r["driver"],
            "driver_name": r["driver"],
            "position": index + 1,
            "tyre": r["tyre"] if pd.notna(r["tyre"]) else None,
            "gap": gap,
            "interval": None,
            "last_lap_time": _format_lap_time(r["last"]),
            "best_lap_time": _format_lap_time(r["best"]),
            "laps_completed": r["laps"],
            "status": "Running" if r["best"] is not None else "No time",
        })
    return positions

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class LivePoller:
    """Live F1 data poller service"""
    
    def __init__(self, redis_url: str, cache_dir: str, race_year: int, race_gp: str,
                 poll_interval: int = 5, session: str = "R"):
        if session not in SESSIONS:
            raise ValueError(f"Unknown session {session!r}; expected one of {', '.join(SESSIONS)}")
        self.session_code = session
        self.redis_url = redis_url
        self.cache_dir = cache_dir
        self.race_year = race_year
        self.race_gp = race_gp
        self.poll_interval = poll_interval
        self.redis_service = RedisService(redis_url)
        # RACE_GP can be a full FastF1-matchable name like "Dutch Grand Prix";
        # only the id derived from it needs normalizing, not the FastF1 lookup.
        self.race_id = build_race_id(race_year, race_gp, session)
        
        # Set FastF1 cache directory
        fastf1.Cache.enable_cache(cache_dir)
        
        # State tracking
        self.last_lap_number = 0
        self.last_positions = {}
        self.session = None
        self.is_polling = False
        self.stall_polls = 0
        
    async def initialize(self):
        """Initialize the poller"""
        await self.redis_service.initialize()
        logger.info(f"✅ Live poller initialized for {self.race_id}")
    
    async def cleanup(self):
        """Cleanup the poller"""
        self.is_polling = False
        await self.redis_service.cleanup()
        logger.info("✅ Live poller cleanup completed")
    
    async def start_polling(self):
        """Start polling for live data"""
        try:
            logger.info(f"🚀 Starting live polling for {self.race_id}")
            logger.info(f"📊 Poll interval: {self.poll_interval} seconds")
            
            self.is_polling = True
            
            while self.is_polling:
                try:
                    # Check if session is available and live
                    if await self._is_session_live():
                        # Poll for updates
                        await self._poll_session_data()
                        if await self._check_session_ended():
                            await self._persist_and_stop()
                            break
                    else:
                        logger.debug(f"⏳ Session not live yet for {self.race_id}")

                    # Wait before next poll
                    await asyncio.sleep(self.poll_interval)
                    
                except KeyboardInterrupt:
                    logger.info("🛑 Polling interrupted by user")
                    break
                except Exception as e:
                    logger.error(f"❌ Error during polling: {str(e)}")
                    # Continue polling with exponential backoff
                    await asyncio.sleep(min(self.poll_interval * 2, 60))
            
        except Exception as e:
            logger.error(f"❌ Error in polling loop: {str(e)}")
        finally:
            self.is_polling = False
            logger.info("🏁 Live polling stopped")
    
    async def _is_session_live(self) -> bool:
        """Check if the session is live or in progress"""
        try:
            if self.session is None:
                self.session = fastf1.get_session(self.race_year, self.race_gp, self.session_code)
            
            # Try to load session data
            self.session.load()
            
            # Check if session has results (race has started)
            if self.session.results is None or self.session.results.empty:
                return False
            
            # Check if session is still in progress
            # This is a simplified check - in practice you'd check session status
            return True
            
        except Exception as e:
            logger.debug(f"Session not available: {str(e)}")
            return False
    
    async def _poll_session_data(self):
        """Poll session data for updates"""
        try:
            if self.session is None:
                return
            
            # Get current lap data
            current_laps = self.session.laps
            
            if current_laps.empty:
                return
            
            # Check if we have new lap data
            latest_lap = current_laps['LapNumber'].max()
            
            if latest_lap > self.last_lap_number:
                logger.info(f"📊 New lap data available: Lap {latest_lap}")
                # Per-lap race positions mean nothing in a timed session.
                if not is_timed_session(self.session_code):
                    await self._process_lap_update(current_laps, latest_lap)
                self.last_lap_number = latest_lap
                self.stall_polls = 0
            else:
                self.stall_polls += 1

            # Always update positions and state
            await self._update_live_state(current_laps)
            
        except Exception as e:
            logger.error(f"❌ Error polling session data: {str(e)}")

    async def _check_session_ended(self) -> bool:
        """Best-effort session-end heuristic: lap count has stalled for a
        few consecutive polls and the session's results show a terminal
        status for the leader (not blank/"Running"). Timed sessions have no such
        status, so they end after a longer stall with no new laps."""
        if is_timed_session(self.session_code):
            needed = -(-TIMED_SESSION_END_STALL_SECONDS // max(self.poll_interval, 1))
            return self.stall_polls >= needed
        if self.stall_polls < SESSION_END_STALL_POLLS:
            return False
        if self.session is None or self.session.results is None or self.session.results.empty:
            return False
        try:
            leader_status = str(self.session.results.iloc[0].get("Status", "")).strip()
        except Exception:
            return False
        return bool(leader_status) and leader_status.lower() != "running"

    async def _persist_and_stop(self):
        """Push this session's results into the database via the API, then
        stop polling — the race is over."""
        logger.info(f"🏁 Session end detected for {self.race_id}, persisting results…")
        headers = {"Content-Type": "application/json"}
        if INTERNAL_API_KEY:
            headers["X-Internal-Key"] = INTERNAL_API_KEY
        payload = {"year": self.race_year, "event": self.race_gp, "laps": False, "session": self.session_code}
        try:
            async with aiohttp.ClientSession() as http:
                async with http.post(
                    f"{API_BASE_URL}/admin/ingest/race", json=payload, headers=headers, timeout=30
                ) as resp:
                    if resp.status == 200:
                        logger.info(f"✅ Ingest triggered for {self.race_id}")
                    else:
                        body = await resp.text()
                        logger.error(f"❌ Ingest trigger failed ({resp.status}): {body}")
        except Exception as e:
            logger.error(f"❌ Error calling /admin/ingest/race: {str(e)}")
        self.is_polling = False

    async def _process_lap_update(self, laps: pd.DataFrame, lap_number: int):
        """Process new lap data"""
        try:
            # Get data for the new lap
            lap_data = laps[laps['LapNumber'] == lap_number]
            
            if lap_data.empty:
                return
            
            # Create update data
            update = {
                "type": "lap_update",
                "lap_number": int(lap_number),
                "timestamp": datetime.utcnow().isoformat(),
                "drivers": []
            }
            
            # Process each driver's lap
            for _, lap in lap_data.iterrows():
                if pd.notna(lap['LapTime']):
                    driver_data = {
                        "driver": lap['Driver'],
                        "lap_time": str(lap['LapTime']),
                        "position": int(lap['Position']),
                        "tyre": lap['Compound'],
                        "sector1": str(lap['Sector1Time']) if pd.notna(lap['Sector1Time']) else None,
                        "sector2": str(lap['Sector2Time']) if pd.notna(lap['Sector2Time']) else None,
                        "sector3": str(lap['Sector3Time']) if pd.notna(lap['Sector3Time']) else None,
                        "pit": lap['PitOutTime'] is not pd.NaT
                    }
                    update["drivers"].append(driver_data)
            
            # Publish update
            await self.redis_service.publish_update(self.race_id, update)
            
            logger.info(f"📡 Published lap {lap_number} update for {self.race_id}")
            
        except Exception as e:
            logger.error(f"❌ Error processing lap update: {str(e)}")
    
    async def _update_live_state(self, laps: pd.DataFrame):
        """Update live state with current positions and data"""
        try:
            if laps.empty:
                return

            if is_timed_session(self.session_code):
                positions = build_timed_positions(laps)
                state = {
                    "race_id": self.race_id,
                    "session": self.session_code,
                    "session_type": "timed",
                    "timestamp": datetime.utcnow().isoformat(),
                    "session_status": "live",
                    "track_status": "green",
                    "leader": positions[0]['driver_id'] if positions else None,
                    "positions": positions,
                }
            else:
                state = self._classified_state(laps)

            # Store state in Redis
            await self.redis_service.set_live_state(self.race_id, state, ttl=3600)
            
            # Publish state update
            await self.redis_service.publish_update(self.race_id, {
                "type": "state_update",
                "timestamp": datetime.utcnow().isoformat(),
                "state": state
            })
            
            logger.debug(f"📡 Updated live state for {self.race_id}")
            
        except Exception as e:
            logger.error(f"❌ Error updating live state: {str(e)}")
    
    def _classified_state(self, laps: pd.DataFrame) -> Dict[str, Any]:
        """Race / sprint: order by FastF1's race Position, with a lap counter."""
        latest_data = laps.groupby('Driver').last()
        total_laps = getattr(self.session, 'total_laps', None)

        # Fields match the frontend LiveState interface
        positions = []
        for driver, data in latest_data.iterrows():
            positions.append({
                "driver_id": driver,
                "driver_name": driver,
                "position": int(data['Position']),
                "tyre": data['Compound'],
                "gap": self._calculate_gap(data, latest_data),
                "interval": None,
                "last_lap_time": str(data['LapTime']) if pd.notna(data['LapTime']) else None,
                "status": "Running",
            })
        positions.sort(key=lambda x: x['position'])

        return {
            "race_id": self.race_id,
            "session": self.session_code,
            "session_type": "classified",
            "timestamp": datetime.utcnow().isoformat(),
            "session_status": "live",
            "track_status": "green",
            "lap": int(latest_data['LapNumber'].max()),
            "total_laps": int(total_laps) if total_laps else None,
            "leader": positions[0]['driver_id'] if positions else None,
            "positions": positions,
        }

    def _calculate_gap(self, driver_data: pd.Series, all_data: pd.DataFrame) -> Optional[str]:
        """Calculate gap to leader"""
        try:
            if all_data.empty:
                return None
            
            # Find leader (position 1)
            leader_data = all_data[all_data['Position'] == 1]
            if leader_data.empty:
                return None
            
            leader_lap_time = leader_data.iloc[0]['LapTime']
            driver_lap_time = driver_data['LapTime']
            
            if pd.isna(leader_lap_time) or pd.isna(driver_lap_time):
                return None
            
            # Calculate gap
            gap = driver_lap_time - leader_lap_time
            
            if gap.total_seconds() < 0:
                return f"+{abs(gap)}"
            else:
                return f"+{gap}"
                
        except Exception:
            return None

async def main():
    """Main poller function"""
    parser = argparse.ArgumentParser(description='Live F1 Data Poller')
    parser.add_argument('--race-year', type=int, default=int(os.environ.get('RACE_YEAR', 2024)), help='Race year')
    parser.add_argument('--race-gp', type=str, default=os.environ.get('RACE_GP', 'Bahrain'), help='Race Grand Prix')
    parser.add_argument('--session', choices=SESSIONS, default=os.environ.get('RACE_SESSION', 'R'), help='Session to follow: FP1/FP2/FP3, SQ (sprint qualifying), S (sprint), Q (qualifying), R (race)')
    parser.add_argument('--poll-interval', type=int, default=int(os.environ.get('POLL_INTERVAL', 5)), help='Poll interval in seconds')
    parser.add_argument('--redis-url', default=os.environ.get('REDIS_URL', 'redis://localhost:6379'), help='Redis URL')
    parser.add_argument('--cache-dir', default=os.environ.get('FASTF1_CACHE_DIR', 'data/fastf1_cache'), help='FastF1 cache directory')
    
    args = parser.parse_args()
    
    # Create poller
    poller = LivePoller(
        redis_url=args.redis_url,
        cache_dir=args.cache_dir,
        race_year=args.race_year,
        race_gp=args.race_gp,
        poll_interval=args.poll_interval,
        session=args.session,
    )
    
    try:
        # Initialize and start polling
        await poller.initialize()
        await poller.start_polling()
    
    except KeyboardInterrupt:
        logger.info("🛑 Poller stopped by user")
    
    except Exception as e:
        logger.error(f"❌ Poller error: {str(e)}")
    
    finally:
        await poller.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
