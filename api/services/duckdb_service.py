"""
DuckDB Service for F1 Historical Data Storage
Handles DuckDB operations and Parquet file management
"""

import duckdb
import pandas as pd
import os
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
import asyncio
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

class DuckDBService:
    """Service for DuckDB operations and historical data management"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.connection = None
        self.executor = ThreadPoolExecutor(max_workers=4)
        
    async def initialize(self):
        """Initialize DuckDB connection and create tables"""
        try:
            # Ensure data directory exists
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            
            # Initialize connection
            self.connection = duckdb.connect(self.db_path)
            
            # Create tables
            await self._create_tables()
            
            logger.info(f"✅ DuckDB initialized at {self.db_path}")
            
        except Exception as e:
            logger.error(f"❌ Error initializing DuckDB: {str(e)}")
            raise
    
    async def cleanup(self):
        """Cleanup DuckDB connection"""
        try:
            if self.connection:
                self.connection.close()
            self.executor.shutdown(wait=True)
            logger.info("✅ DuckDB cleanup completed")
        except Exception as e:
            logger.error(f"❌ Error during DuckDB cleanup: {str(e)}")
    
    async def _create_tables(self):
        """Create DuckDB tables for F1 data"""
        try:
            # Drivers table
            self.connection.execute("""
                CREATE TABLE IF NOT EXISTS drivers (
                    driver_id VARCHAR PRIMARY KEY,
                    full_name VARCHAR NOT NULL,
                    nationality VARCHAR,
                    number INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Constructors table
            self.connection.execute("""
                CREATE TABLE IF NOT EXISTS constructors (
                    constructor_id VARCHAR PRIMARY KEY,
                    constructor_name VARCHAR NOT NULL,
                    nationality VARCHAR,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Races table
            self.connection.execute("""
                CREATE TABLE IF NOT EXISTS races (
                    race_id VARCHAR PRIMARY KEY,
                    year INTEGER NOT NULL,
                    round INTEGER NOT NULL,
                    gp VARCHAR NOT NULL,
                    date DATE,
                    circuit_name VARCHAR,
                    country VARCHAR,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Race results table
            self.connection.execute("""
                CREATE TABLE IF NOT EXISTS race_results (
                    id INTEGER PRIMARY KEY,
                    race_id VARCHAR NOT NULL,
                    position INTEGER,
                    driver_id VARCHAR,
                    constructor_id VARCHAR,
                    points FLOAT,
                    time VARCHAR,
                    fastest_lap BOOLEAN,
                    fastest_lap_time VARCHAR,
                    status VARCHAR,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (race_id) REFERENCES races(race_id),
                    FOREIGN KEY (driver_id) REFERENCES drivers(driver_id),
                    FOREIGN KEY (constructor_id) REFERENCES constructors(constructor_id)
                )
            """)
            
            # Telemetry files table
            self.connection.execute("""
                CREATE TABLE IF NOT EXISTS telemetry_files (
                    id INTEGER PRIMARY KEY,
                    race_id VARCHAR NOT NULL,
                    driver_id VARCHAR,
                    session_type VARCHAR,
                    file_path VARCHAR NOT NULL,
                    file_size INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (race_id) REFERENCES races(race_id),
                    FOREIGN KEY (driver_id) REFERENCES drivers(driver_id)
                )
            """)
            
            # Laps table (for aggregated lap data)
            self.connection.execute("""
                CREATE TABLE IF NOT EXISTS laps (
                    id INTEGER PRIMARY KEY,
                    race_id VARCHAR NOT NULL,
                    driver_id VARCHAR,
                    lap_number INTEGER,
                    lap_time_ms INTEGER,
                    sector1_ms INTEGER,
                    sector2_ms INTEGER,
                    sector3_ms INTEGER,
                    tyre VARCHAR,
                    pit BOOLEAN,
                    position INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (race_id) REFERENCES races(race_id),
                    FOREIGN KEY (driver_id) REFERENCES drivers(driver_id)
                )
            """)
            
            logger.info("✅ DuckDB tables created successfully")
            
        except Exception as e:
            logger.error(f"❌ Error creating DuckDB tables: {str(e)}")
            raise
    
    async def _run_query(self, query: str, params: tuple = None) -> List[Dict]:
        """Run a query in thread pool to avoid blocking"""
        def _execute():
            if params:
                result = self.connection.execute(query, params).fetchall()
            else:
                result = self.connection.execute(query).fetchall()
            
            # Get column names
            columns = [desc[0] for desc in self.connection.description]
            
            # Convert to list of dictionaries
            return [dict(zip(columns, row)) for row in result]
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, _execute)
    
    async def get_drivers_by_year(self, year: int) -> List[Dict]:
        """Get drivers who raced in a specific year"""
        try:
            query = """
                SELECT DISTINCT d.driver_id, d.full_name, d.nationality, d.number
                FROM drivers d
                JOIN race_results rr ON d.driver_id = rr.driver_id
                JOIN races r ON rr.race_id = r.race_id
                WHERE r.year = ?
                ORDER BY d.full_name
            """
            return await self._run_query(query, (year,))
            
        except Exception as e:
            logger.error(f"❌ Error fetching drivers by year: {str(e)}")
            return []
    
    async def get_all_drivers(self) -> List[Dict]:
        """Get all drivers from database"""
        try:
            query = """
                SELECT driver_id, full_name, nationality, number
                FROM drivers
                ORDER BY full_name
            """
            return await self._run_query(query)
            
        except Exception as e:
            logger.error(f"❌ Error fetching all drivers: {str(e)}")
            return []
    
    async def get_driver_details(self, driver_id: str, year: int) -> Optional[Dict]:
        """Get detailed information about a specific driver"""
        try:
            query = """
                SELECT d.*, 
                       COUNT(rr.race_id) as races_entered,
                       SUM(rr.points) as total_points,
                       COUNT(CASE WHEN rr.position = 1 THEN 1 END) as wins
                FROM drivers d
                LEFT JOIN race_results rr ON d.driver_id = rr.driver_id
                LEFT JOIN races r ON rr.race_id = r.race_id AND r.year = ?
                WHERE d.driver_id = ?
                GROUP BY d.driver_id, d.full_name, d.nationality, d.number
            """
            results = await self._run_query(query, (year, driver_id))
            return results[0] if results else None
            
        except Exception as e:
            logger.error(f"❌ Error fetching driver details: {str(e)}")
            return None
    
    async def get_races_by_year(self, year: int) -> List[Dict]:
        """Get races for a specific year"""
        try:
            query = """
                SELECT race_id, year, round, gp, date, circuit_name, country
                FROM races
                WHERE year = ?
                ORDER BY round
            """
            return await self._run_query(query, (year,))
            
        except Exception as e:
            logger.error(f"❌ Error fetching races by year: {str(e)}")
            return []
    
    async def get_race_results(self, race_id: str) -> List[Dict]:
        """Get race results for a specific race"""
        try:
            query = """
                SELECT rr.position, d.full_name as driver_name, c.constructor_name,
                       rr.points, rr.time, rr.fastest_lap, rr.fastest_lap_time, rr.status
                FROM race_results rr
                LEFT JOIN drivers d ON rr.driver_id = d.driver_id
                LEFT JOIN constructors c ON rr.constructor_id = c.constructor_id
                WHERE rr.race_id = ?
                ORDER BY rr.position
            """
            return await self._run_query(query, (race_id,))
            
        except Exception as e:
            logger.error(f"❌ Error fetching race results: {str(e)}")
            return []
    
    async def get_race_laps(self, race_id: str, driver: Optional[str] = None) -> List[Dict]:
        """Get lap data for a race, optionally filtered by driver"""
        try:
            if driver:
                query = """
                    SELECT l.lap_number, l.lap_time_ms, l.sector1_ms, l.sector2_ms, 
                           l.sector3_ms, l.tyre, l.pit, l.position, d.full_name as driver_name
                    FROM laps l
                    LEFT JOIN drivers d ON l.driver_id = d.driver_id
                    WHERE l.race_id = ? AND d.driver_id = ?
                    ORDER BY l.lap_number
                """
                return await self._run_query(query, (race_id, driver))
            else:
                query = """
                    SELECT l.lap_number, l.lap_time_ms, l.sector1_ms, l.sector2_ms, 
                           l.sector3_ms, l.tyre, l.pit, l.position, d.full_name as driver_name
                    FROM laps l
                    LEFT JOIN drivers d ON l.driver_id = d.driver_id
                    WHERE l.race_id = ?
                    ORDER BY l.lap_number, l.position
                """
                return await self._run_query(query, (race_id,))
                
        except Exception as e:
            logger.error(f"❌ Error fetching race laps: {str(e)}")
            return []
    
    async def store_drivers(self, drivers: List[Dict]) -> bool:
        """Store drivers data in DuckDB"""
        try:
            if not drivers:
                return True
                
            # Convert to DataFrame
            df = pd.DataFrame(drivers)
            
            # Insert or replace drivers
            self.connection.execute("""
                INSERT OR REPLACE INTO drivers (driver_id, full_name, nationality, number)
                SELECT driver_id, full_name, nationality, number FROM df
            """, {"df": df})
            
            logger.info(f"✅ Stored {len(drivers)} drivers in DuckDB")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error storing drivers: {str(e)}")
            return False
    
    async def store_constructors(self, constructors: List[Dict]) -> bool:
        """Store constructors data in DuckDB"""
        try:
            if not constructors:
                return True
                
            df = pd.DataFrame(constructors)
            
            self.connection.execute("""
                INSERT OR REPLACE INTO constructors (constructor_id, constructor_name, nationality)
                SELECT constructor_id, constructor_name, nationality FROM df
            """, {"df": df})
            
            logger.info(f"✅ Stored {len(constructors)} constructors in DuckDB")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error storing constructors: {str(e)}")
            return False
    
    async def store_races(self, races: List[Dict]) -> bool:
        """Store races data in DuckDB"""
        try:
            if not races:
                return True
                
            df = pd.DataFrame(races)
            
            self.connection.execute("""
                INSERT OR REPLACE INTO races (race_id, year, round, gp, date, circuit_name, country)
                SELECT race_id, year, round, gp, date, circuit_name, country FROM df
            """, {"df": df})
            
            logger.info(f"✅ Stored {len(races)} races in DuckDB")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error storing races: {str(e)}")
            return False
    
    async def store_race_results(self, race_id: str, results: List[Dict]) -> bool:
        """Store race results in DuckDB"""
        try:
            if not results:
                return True
                
            # Add race_id to each result
            for result in results:
                result['race_id'] = race_id
                
            df = pd.DataFrame(results)
            
            self.connection.execute("""
                INSERT OR REPLACE INTO race_results 
                (race_id, position, driver_id, constructor_id, points, time, fastest_lap, fastest_lap_time, status)
                SELECT race_id, position, driver_id, constructor_id, points, time, fastest_lap, fastest_lap_time, status FROM df
            """, {"df": df})
            
            logger.info(f"✅ Stored {len(results)} race results for {race_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error storing race results: {str(e)}")
            return False
    
    async def store_telemetry_file(self, race_id: str, driver_id: str, session_type: str, 
                                 file_path: str, file_size: int) -> bool:
        """Store telemetry file reference in DuckDB"""
        try:
            self.connection.execute("""
                INSERT INTO telemetry_files (race_id, driver_id, session_type, file_path, file_size)
                VALUES (?, ?, ?, ?, ?)
            """, (race_id, driver_id, session_type, file_path, file_size))
            
            logger.info(f"✅ Stored telemetry file reference: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error storing telemetry file: {str(e)}")
            return False
    
    async def store_laps(self, race_id: str, laps: List[Dict]) -> bool:
        """Store lap data in DuckDB"""
        try:
            if not laps:
                return True
                
            # Add race_id to each lap
            for lap in laps:
                lap['race_id'] = race_id
                
            df = pd.DataFrame(laps)
            
            self.connection.execute("""
                INSERT OR REPLACE INTO laps 
                (race_id, driver_id, lap_number, lap_time_ms, sector1_ms, sector2_ms, 
                 sector3_ms, tyre, pit, position)
                SELECT race_id, driver_id, lap_number, lap_time_ms, sector1_ms, sector2_ms, 
                       sector3_ms, tyre, pit, position FROM df
            """, {"df": df})
            
            logger.info(f"✅ Stored {len(laps)} laps for {race_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error storing laps: {str(e)}")
            return False
