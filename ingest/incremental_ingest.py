#!/usr/bin/env python3
"""
Incremental Data Ingestion Script
Idempotent incremental loader for newly available F1 sessions
"""

import asyncio
import argparse
import logging
import os
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Any, Set
import pandas as pd
import fastf1
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.services.duckdb_service import DuckDBService
from api.services.fastf1_service import FastF1Service
from api.services.ergast_service import ErgastService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class IncrementalIngester:
    """Incremental data ingestion service"""
    
    def __init__(self, db_path: str, telemetry_dir: str, cache_dir: str):
        self.db_path = db_path
        self.telemetry_dir = Path(telemetry_dir)
        self.cache_dir = cache_dir
        self.duckdb_service = DuckDBService(db_path)
        self.fastf1_service = FastF1Service()
        self.ergast_service = ErgastService()
        
        # Ensure telemetry directory exists
        self.telemetry_dir.mkdir(parents=True, exist_ok=True)
        
        # Set FastF1 cache directory
        fastf1.Cache.enable_cache(cache_dir)
        
    async def initialize(self):
        """Initialize services"""
        await self.duckdb_service.initialize()
        logger.info("✅ Incremental ingester initialized")
    
    async def cleanup(self):
        """Cleanup services"""
        await self.duckdb_service.cleanup()
        logger.info("✅ Incremental ingester cleanup completed")
    
    async def check_for_new_sessions(self, years: List[int] = None) -> List[Dict[str, Any]]:
        """Check for new sessions that haven't been ingested yet"""
        try:
            if years is None:
                # Check current year and previous year
                current_year = datetime.now().year
                years = [current_year - 1, current_year]
            
            new_sessions = []
            
            for year in years:
                logger.info(f"🔍 Checking for new sessions in {year}...")
                
                # Get existing race IDs from database
                existing_races = await self._get_existing_race_ids(year)
                
                # Get available sessions from FastF1
                available_sessions = await self._get_available_sessions(year)
                
                # Find new sessions
                for session in available_sessions:
                    race_id = f"{year}_{session['gp']}"
                    if race_id not in existing_races:
                        new_sessions.append({
                            'year': year,
                            'gp': session['gp'],
                            'race_id': race_id,
                            'session_type': session.get('session_type', 'R'),
                            'date': session.get('date')
                        })
            
            logger.info(f"📊 Found {len(new_sessions)} new sessions to ingest")
            return new_sessions
            
        except Exception as e:
            logger.error(f"❌ Error checking for new sessions: {str(e)}")
            return []
    
    async def ingest_new_sessions(self, sessions: List[Dict[str, Any]]) -> bool:
        """Ingest new sessions"""
        try:
            if not sessions:
                logger.info("ℹ️ No new sessions to ingest")
                return True
            
            success_count = 0
            
            for session in sessions:
                try:
                    logger.info(f"📊 Ingesting session: {session['race_id']}")
                    
                    # Check if session data is available
                    if not await self._is_session_available(session['year'], session['gp']):
                        logger.warning(f"⚠️ Session data not available for {session['race_id']}")
                        continue
                    
                    # Ingest the session
                    success = await self._ingest_session(session)
                    if success:
                        success_count += 1
                        logger.info(f"✅ Successfully ingested {session['race_id']}")
                    else:
                        logger.error(f"❌ Failed to ingest {session['race_id']}")
                
                except Exception as e:
                    logger.error(f"❌ Error ingesting session {session['race_id']}: {str(e)}")
                    continue
            
            logger.info(f"🏁 Ingested {success_count}/{len(sessions)} new sessions")
            return success_count > 0
            
        except Exception as e:
            logger.error(f"❌ Error ingesting new sessions: {str(e)}")
            return False
    
    async def _get_existing_race_ids(self, year: int) -> Set[str]:
        """Get existing race IDs from database"""
        try:
            races = await self.duckdb_service.get_races_by_year(year)
            return {race['race_id'] for race in races}
        except Exception as e:
            logger.error(f"❌ Error getting existing race IDs: {str(e)}")
            return set()
    
    async def _get_available_sessions(self, year: int) -> List[Dict[str, Any]]:
        """Get available sessions from FastF1"""
        try:
            # Get race schedule
            if year >= 2020:
                schedule = await self.fastf1_service.get_race_schedule(year)
            else:
                async with self.ergast_service as ergast:
                    schedule = await ergast.get_race_schedule(year)
            
            sessions = []
            for i, race in enumerate(schedule, 1):
                sessions.append({
                    'gp': race.get('gp', f'Race_{i}'),
                    'date': race.get('date'),
                    'session_type': 'R'  # Default to race session
                })
            
            return sessions
            
        except Exception as e:
            logger.error(f"❌ Error getting available sessions for {year}: {str(e)}")
            return []
    
    async def _is_session_available(self, year: int, gp: str) -> bool:
        """Check if session data is available"""
        try:
            session = fastf1.get_session(year, gp, 'R')
            session.load()
            return session.results is not None and not session.results.empty
        except Exception as e:
            logger.debug(f"Session not available for {year} {gp}: {str(e)}")
            return False
    
    async def _ingest_session(self, session: Dict[str, Any]) -> bool:
        """Ingest a single session"""
        try:
            year = session['year']
            gp = session['gp']
            race_id = session['race_id']
            
            # Get race data
            race_data = [{
                'race_id': race_id,
                'year': year,
                'round': await self._get_race_round(year, gp),
                'gp': gp,
                'date': session.get('date'),
                'circuit_name': await self._get_circuit_name(year, gp),
                'country': await self._get_country(year, gp)
            }]
            
            # Store race data
            await self.duckdb_service.store_races(race_data)
            
            # Get and store race results
            results = await self._get_race_results(year, gp)
            if results:
                await self.duckdb_service.store_race_results(race_id, results)
            
            # Process telemetry
            await self._process_session_telemetry(year, gp, race_id)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error ingesting session {session['race_id']}: {str(e)}")
            return False
    
    async def _get_race_round(self, year: int, gp: str) -> int:
        """Get race round number"""
        try:
            # This is a simplified implementation
            # In practice, you'd query the database or API for the actual round
            return 1  # Placeholder
        except Exception:
            return 1
    
    async def _get_circuit_name(self, year: int, gp: str) -> str:
        """Get circuit name"""
        try:
            session = fastf1.get_session(year, gp, 'R')
            return session.event['Location']
        except Exception:
            return 'Unknown'
    
    async def _get_country(self, year: int, gp: str) -> str:
        """Get country name"""
        try:
            session = fastf1.get_session(year, gp, 'R')
            return session.event['Country']
        except Exception:
            return 'Unknown'
    
    async def _get_race_results(self, year: int, gp: str) -> List[Dict]:
        """Get race results"""
        try:
            results = await self.fastf1_service.get_race_results(year, gp)
            
            formatted_results = []
            for result in results:
                formatted_results.append({
                    'position': result.get('position', 0),
                    'driver_id': result.get('driver_id', ''),
                    'constructor_id': result.get('constructor_id', ''),
                    'points': result.get('points', 0),
                    'time': result.get('time', ''),
                    'fastest_lap': result.get('fastest_lap', False),
                    'fastest_lap_time': result.get('fastest_lap_time', ''),
                    'status': result.get('status', '')
                })
            
            return formatted_results
            
        except Exception as e:
            logger.error(f"❌ Error getting race results: {str(e)}")
            return []
    
    async def _process_session_telemetry(self, year: int, gp: str, race_id: str):
        """Process telemetry data for a session"""
        try:
            session = fastf1.get_session(year, gp, 'R')
            session.load()
            
            if session.results is None or session.results.empty:
                logger.warning(f"⚠️ No results data for {race_id}")
                return
            
            # Process lap data
            laps_data = []
            for _, lap in session.laps.iterrows():
                if pd.notna(lap['LapTime']):
                    laps_data.append({
                        'driver_id': lap['Driver'],
                        'lap_number': lap['LapNumber'],
                        'lap_time_ms': int(lap['LapTime'].total_seconds() * 1000) if pd.notna(lap['LapTime']) else None,
                        'sector1_ms': int(lap['Sector1Time'].total_seconds() * 1000) if pd.notna(lap['Sector1Time']) else None,
                        'sector2_ms': int(lap['Sector2Time'].total_seconds() * 1000) if pd.notna(lap['Sector2Time']) else None,
                        'sector3_ms': int(lap['Sector3Time'].total_seconds() * 1000) if pd.notna(lap['Sector3Time']) else None,
                        'tyre': lap['Compound'],
                        'pit': lap['PitOutTime'] is not pd.NaT,
                        'position': lap['Position']
                    })
            
            # Store lap data
            if laps_data:
                await self.duckdb_service.store_laps(race_id, laps_data)
            
            # Save telemetry as Parquet
            await self._save_telemetry_parquet(session, race_id)
            
        except Exception as e:
            logger.error(f"❌ Error processing telemetry for {race_id}: {str(e)}")
    
    async def _save_telemetry_parquet(self, session, race_id: str):
        """Save telemetry data as Parquet files"""
        try:
            race_dir = self.telemetry_dir / race_id
            race_dir.mkdir(exist_ok=True)
            
            # Save laps data
            laps_file = race_dir / "laps.parquet"
            session.laps.to_parquet(laps_file)
            
            # Save results data
            results_file = race_dir / "results.parquet"
            session.results.to_parquet(results_file)
            
            # Save telemetry for each driver
            for driver in session.results['Abbreviation']:
                try:
                    driver_laps = session.laps[session.laps['Driver'] == driver]
                    if not driver_laps.empty:
                        telemetry = session.get_driver(driver).telemetry
                        if not telemetry.empty:
                            telemetry_file = race_dir / f"{driver}_telemetry.parquet"
                            telemetry.to_parquet(telemetry_file)
                            
                            await self.duckdb_service.store_telemetry_file(
                                race_id, driver, 'R', str(telemetry_file), 
                                telemetry_file.stat().st_size
                            )
                            
                except Exception as e:
                    logger.warning(f"⚠️ Error saving telemetry for driver {driver}: {str(e)}")
                    continue
            
            logger.info(f"✅ Saved telemetry data for {race_id}")
            
        except Exception as e:
            logger.error(f"❌ Error saving telemetry parquet for {race_id}: {str(e)}")

async def main():
    """Main incremental ingestion function"""
    parser = argparse.ArgumentParser(description='Incremental F1 Data Ingestion')
    parser.add_argument('--years', nargs='+', type=int, help='Years to check (default: current and previous year)')
    parser.add_argument('--db-path', default='data/f1_history.duckdb', help='DuckDB database path')
    parser.add_argument('--telemetry-dir', default='data/telemetry', help='Telemetry data directory')
    parser.add_argument('--cache-dir', default='data/fastf1_cache', help='FastF1 cache directory')
    parser.add_argument('--dry-run', action='store_true', help='Only check for new sessions, don\'t ingest')
    
    args = parser.parse_args()
    
    # Determine years to check
    if args.years:
        years = args.years
    else:
        current_year = datetime.now().year
        years = [current_year - 1, current_year]
    
    logger.info(f"🔍 Checking for new sessions in years: {years}")
    
    # Initialize ingester
    ingester = IncrementalIngester(args.db_path, args.telemetry_dir, args.cache_dir)
    await ingester.initialize()
    
    try:
        # Check for new sessions
        new_sessions = await ingester.check_for_new_sessions(years)
        
        if not new_sessions:
            logger.info("ℹ️ No new sessions found")
            return
        
        logger.info(f"📊 Found {len(new_sessions)} new sessions:")
        for session in new_sessions:
            logger.info(f"  - {session['race_id']} ({session.get('date', 'Unknown date')})")
        
        if not args.dry_run:
            # Ingest new sessions
            success = await ingester.ingest_new_sessions(new_sessions)
            if success:
                logger.info("✅ Incremental ingestion completed successfully")
            else:
                logger.error("❌ Incremental ingestion failed")
        else:
            logger.info("🔍 Dry run completed - no data ingested")
    
    finally:
        await ingester.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
