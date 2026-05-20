#!/usr/bin/env python3
"""
Historical Data Ingestion Script
Batch ingest historical F1 seasons into DuckDB and store telemetry as Parquet files
"""

import asyncio
import argparse
import logging
import os
import sys
from datetime import datetime
from typing import List, Dict, Any
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

class HistoricalIngester:
    """Historical data ingestion service"""
    
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
        logger.info("✅ Historical ingester initialized")
    
    async def cleanup(self):
        """Cleanup services"""
        await self.duckdb_service.cleanup()
        logger.info("✅ Historical ingester cleanup completed")
    
    async def ingest_season(self, year: int) -> bool:
        """Ingest data for a specific season"""
        try:
            logger.info(f"🚀 Starting ingestion for {year} season...")
            
            # Get race schedule
            races = await self._get_race_schedule(year)
            if not races:
                logger.warning(f"⚠️ No races found for {year}")
                return False
            
            # Store races in DuckDB
            await self.duckdb_service.store_races(races)
            
            # Get drivers and constructors
            drivers = await self._get_drivers(year)
            constructors = await self._get_constructors(year)
            
            await self.duckdb_service.store_drivers(drivers)
            await self.duckdb_service.store_constructors(constructors)
            
            # Process each race
            for race in races:
                race_id = f"{year}_{race['gp']}"
                logger.info(f"📊 Processing race: {race_id}")
                
                try:
                    # Get race results
                    results = await self._get_race_results(year, race['gp'])
                    if results:
                        await self.duckdb_service.store_race_results(race_id, results)
                    
                    # Get lap data and telemetry
                    await self._process_race_telemetry(year, race['gp'], race_id)
                    
                except Exception as e:
                    logger.error(f"❌ Error processing race {race_id}: {str(e)}")
                    continue
            
            logger.info(f"✅ Completed ingestion for {year} season")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error ingesting season {year}: {str(e)}")
            return False
    
    async def _get_race_schedule(self, year: int) -> List[Dict]:
        """Get race schedule for a year"""
        try:
            # Try FastF1 first for recent years
            if year >= 2020:
                schedule = await self.fastf1_service.get_race_schedule(year)
            else:
                # Use Ergast for historical data
                async with self.ergast_service as ergast:
                    schedule = await ergast.get_race_schedule(year)
            
            # Convert to our format
            races = []
            for i, race in enumerate(schedule, 1):
                races.append({
                    'race_id': f"{year}_{race.get('gp', f'Race_{i}')}",
                    'year': year,
                    'round': i,
                    'gp': race.get('gp', f'Race_{i}'),
                    'date': race.get('date'),
                    'circuit_name': race.get('circuit_name', 'Unknown'),
                    'country': race.get('country', 'Unknown')
                })
            
            return races
            
        except Exception as e:
            logger.error(f"❌ Error getting race schedule for {year}: {str(e)}")
            return []
    
    async def _get_drivers(self, year: int) -> List[Dict]:
        """Get drivers for a year"""
        try:
            if year >= 2020:
                standings = await self.fastf1_service.get_driver_standings(year)
            else:
                async with self.ergast_service as ergast:
                    standings = await ergast.get_driver_standings(year)
            
            drivers = []
            for standing in standings:
                drivers.append({
                    'driver_id': standing.get('driver_id', ''),
                    'full_name': standing.get('driver_name', ''),
                    'nationality': standing.get('nationality', ''),
                    'number': standing.get('number', 0)
                })
            
            return drivers
            
        except Exception as e:
            logger.error(f"❌ Error getting drivers for {year}: {str(e)}")
            return []
    
    async def _get_constructors(self, year: int) -> List[Dict]:
        """Get constructors for a year"""
        try:
            if year >= 2020:
                standings = await self.fastf1_service.get_constructor_standings(year)
            else:
                async with self.ergast_service as ergast:
                    standings = await ergast.get_constructor_standings(year)
            
            constructors = []
            for standing in standings:
                constructors.append({
                    'constructor_id': standing.get('constructor_id', ''),
                    'constructor_name': standing.get('constructor_name', ''),
                    'nationality': standing.get('nationality', '')
                })
            
            return constructors
            
        except Exception as e:
            logger.error(f"❌ Error getting constructors for {year}: {str(e)}")
            return []
    
    async def _get_race_results(self, year: int, gp: str) -> List[Dict]:
        """Get race results for a specific race"""
        try:
            results = await self.fastf1_service.get_race_results(year, gp)
            
            # Convert to our format
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
            logger.error(f"❌ Error getting race results for {year} {gp}: {str(e)}")
            return []
    
    async def _process_race_telemetry(self, year: int, gp: str, race_id: str):
        """Process telemetry data for a race"""
        try:
            # Get session data
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
            
            # Store lap data in DuckDB
            if laps_data:
                await self.duckdb_service.store_laps(race_id, laps_data)
            
            # Save telemetry data as Parquet files
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
                        # Get telemetry data
                        telemetry = session.get_driver(driver).telemetry
                        if not telemetry.empty:
                            telemetry_file = race_dir / f"{driver}_telemetry.parquet"
                            telemetry.to_parquet(telemetry_file)
                            
                            # Store file reference in DuckDB
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
    """Main ingestion function"""
    parser = argparse.ArgumentParser(description='Historical F1 Data Ingestion')
    parser.add_argument('--years', nargs='+', type=int, help='Years to ingest (e.g., --years 2023 2024)')
    parser.add_argument('--start-year', type=int, help='Start year for range ingestion')
    parser.add_argument('--end-year', type=int, help='End year for range ingestion')
    parser.add_argument('--db-path', default='data/f1_history.duckdb', help='DuckDB database path')
    parser.add_argument('--telemetry-dir', default='data/telemetry', help='Telemetry data directory')
    parser.add_argument('--cache-dir', default='data/fastf1_cache', help='FastF1 cache directory')
    
    args = parser.parse_args()
    
    # Determine years to process
    if args.years:
        years = args.years
    elif args.start_year and args.end_year:
        years = list(range(args.start_year, args.end_year + 1))
    else:
        # Default to current year
        years = [datetime.now().year]
    
    logger.info(f"🎯 Ingesting data for years: {years}")
    
    # Initialize ingester
    ingester = HistoricalIngester(args.db_path, args.telemetry_dir, args.cache_dir)
    await ingester.initialize()
    
    try:
        # Process each year
        for year in years:
            success = await ingester.ingest_season(year)
            if success:
                logger.info(f"✅ Successfully ingested {year}")
            else:
                logger.error(f"❌ Failed to ingest {year}")
    
    finally:
        await ingester.cleanup()
    
    logger.info("🏁 Historical ingestion completed")

if __name__ == "__main__":
    asyncio.run(main())
