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
import pandas as pd
import fastf1
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.services.redis_service import RedisService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class LivePoller:
    """Live F1 data poller service"""
    
    def __init__(self, redis_url: str, cache_dir: str, race_year: int, race_gp: str, poll_interval: int = 5):
        self.redis_url = redis_url
        self.cache_dir = cache_dir
        self.race_year = race_year
        self.race_gp = race_gp
        self.poll_interval = poll_interval
        self.redis_service = RedisService(redis_url)
        self.race_id = f"{race_year}_{race_gp}"
        
        # Set FastF1 cache directory
        fastf1.Cache.enable_cache(cache_dir)
        
        # State tracking
        self.last_lap_number = 0
        self.last_positions = {}
        self.session = None
        self.is_polling = False
        
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
                self.session = fastf1.get_session(self.race_year, self.race_gp, 'R')
            
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
                await self._process_lap_update(current_laps, latest_lap)
                self.last_lap_number = latest_lap
            
            # Always update positions and state
            await self._update_live_state(current_laps)
            
        except Exception as e:
            logger.error(f"❌ Error polling session data: {str(e)}")
    
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

            # Get latest data for each driver
            latest_data = laps.groupby('Driver').last()
            total_laps = getattr(self.session, 'total_laps', None)

            # Create positions array (fields match frontend LiveState interface)
            positions = []
            for driver, data in latest_data.iterrows():
                position_data = {
                    "driver_id": driver,
                    "driver_name": driver,
                    "position": int(data['Position']),
                    "tyre": data['Compound'],
                    "gap": self._calculate_gap(data, latest_data),
                    "interval": None,
                    "last_lap_time": str(data['LapTime']) if pd.notna(data['LapTime']) else None,
                    "status": "Running",
                }
                positions.append(position_data)

            # Sort by position
            positions.sort(key=lambda x: x['position'])

            current_lap = int(latest_data['LapNumber'].max())
            state = {
                "race_id": self.race_id,
                "timestamp": datetime.utcnow().isoformat(),
                "session_status": "live",
                "track_status": "green",
                "lap": current_lap,
                "total_laps": int(total_laps) if total_laps else None,
                "leader": positions[0]['driver_id'] if positions else None,
                "positions": positions,
            }
            
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
    parser.add_argument('--race-year', type=int, default=2024, help='Race year')
    parser.add_argument('--race-gp', type=str, default='Bahrain', help='Race Grand Prix')
    parser.add_argument('--poll-interval', type=int, default=5, help='Poll interval in seconds')
    parser.add_argument('--redis-url', default='redis://localhost:6379', help='Redis URL')
    parser.add_argument('--cache-dir', default='data/fastf1_cache', help='FastF1 cache directory')
    
    args = parser.parse_args()
    
    # Create poller
    poller = LivePoller(
        redis_url=args.redis_url,
        cache_dir=args.cache_dir,
        race_year=args.race_year,
        race_gp=args.race_gp,
        poll_interval=args.poll_interval
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
