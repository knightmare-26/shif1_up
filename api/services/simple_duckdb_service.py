"""
Simplified DuckDB Service for F1 Historical Data Storage
Provides DuckDB functionality with fallback to in-memory storage
"""

import json
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
import asyncio
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

class SimpleDuckDBService:
    """Simplified DuckDB service with in-memory fallback"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.connection = None
        self.executor = ThreadPoolExecutor(max_workers=2)
        self.in_memory_data = {
            "drivers": [],
            "constructors": [],
            "races": [],
            "race_results": {},
            "laps": {},
            "telemetry_files": []
        }
        
    async def initialize(self):
        """Initialize DuckDB connection or fallback to in-memory"""
        try:
            # Try to import and use DuckDB
            import duckdb
            import os
            
            # Ensure data directory exists
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            
            # Initialize connection
            self.connection = duckdb.connect(self.db_path)
            
            # Create tables
            await self._create_tables()
            
            logger.info(f"✅ DuckDB initialized at {self.db_path}")
            
        except ImportError:
            logger.warning("⚠️ DuckDB not available, using in-memory storage")
            self.connection = None
        except Exception as e:
            logger.warning(f"⚠️ DuckDB initialization failed: {str(e)}, using in-memory storage")
            self.connection = None
    
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
        if not self.connection:
            return
            
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
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Laps table
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
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            logger.info("✅ DuckDB tables created successfully")
            
        except Exception as e:
            logger.error(f"❌ Error creating DuckDB tables: {str(e)}")
            raise
    
    async def _run_query(self, query: str, params: tuple = None) -> List[Dict]:
        """Run a query in thread pool to avoid blocking"""
        if not self.connection:
            return []
            
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
            if self.connection:
                query = """
                    SELECT DISTINCT d.driver_id, d.full_name, d.nationality, d.number
                    FROM drivers d
                    JOIN race_results rr ON d.driver_id = rr.driver_id
                    JOIN races r ON rr.race_id = r.race_id
                    WHERE r.year = ?
                    ORDER BY d.full_name
                """
                return await self._run_query(query, (year,))
            else:
                # Fallback to in-memory data
                return self.in_memory_data["drivers"]
                
        except Exception as e:
            logger.error(f"❌ Error fetching drivers by year: {str(e)}")
            return []
    
    async def get_all_drivers(self) -> List[Dict]:
        """Get all drivers from database"""
        try:
            if self.connection:
                query = """
                    SELECT driver_id, full_name, nationality, number
                    FROM drivers
                    ORDER BY full_name
                """
                return await self._run_query(query)
            else:
                return self.in_memory_data["drivers"]
                
        except Exception as e:
            logger.error(f"❌ Error fetching all drivers: {str(e)}")
            return []
    
    async def get_driver_details(self, driver_id: str, year: int) -> Optional[Dict]:
        """Get detailed information about a specific driver"""
        try:
            if self.connection:
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
            else:
                # Fallback to in-memory data
                for driver in self.in_memory_data["drivers"]:
                    if driver["driver_id"] == driver_id:
                        return driver
                return None
                
        except Exception as e:
            logger.error(f"❌ Error fetching driver details: {str(e)}")
            return None
    
    async def get_races_by_year(self, year: int) -> List[Dict]:
        """Get races for a specific year"""
        try:
            if self.connection:
                query = """
                    SELECT race_id, year, round, gp, date, circuit_name, country
                    FROM races
                    WHERE year = ?
                    ORDER BY round
                """
                return await self._run_query(query, (year,))
            else:
                # Fallback to in-memory data
                return [race for race in self.in_memory_data["races"] if race["year"] == year]
                
        except Exception as e:
            logger.error(f"❌ Error fetching races by year: {str(e)}")
            return []
    
    async def get_race_results(self, race_id: str) -> List[Dict]:
        """Get race results for a specific race"""
        try:
            if self.connection:
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
            else:
                # Fallback to in-memory data
                return self.in_memory_data["race_results"].get(race_id, [])
                
        except Exception as e:
            logger.error(f"❌ Error fetching race results: {str(e)}")
            return []
    
    async def get_race_laps(self, race_id: str, driver: Optional[str] = None) -> List[Dict]:
        """Get lap data for a race, optionally filtered by driver"""
        try:
            if self.connection:
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
            else:
                # Fallback to in-memory data
                laps = self.in_memory_data["laps"].get(race_id, [])
                if driver:
                    return [lap for lap in laps if lap.get("driver_id") == driver]
                return laps
                
        except Exception as e:
            logger.error(f"❌ Error fetching race laps: {str(e)}")
            return []
    
    async def store_drivers(self, drivers: List[Dict]) -> bool:
        """Store drivers data in DuckDB or memory"""
        try:
            if not drivers:
                return True
                
            if self.connection:
                import pandas as pd
                df = pd.DataFrame(drivers)
                self.connection.execute("""
                    INSERT OR REPLACE INTO drivers (driver_id, full_name, nationality, number)
                    SELECT driver_id, full_name, nationality, number FROM df
                """, {"df": df})
            else:
                # Store in memory
                self.in_memory_data["drivers"] = drivers
            
            logger.info(f"✅ Stored {len(drivers)} drivers")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error storing drivers: {str(e)}")
            return False
    
    async def store_constructors(self, constructors: List[Dict]) -> bool:
        """Store constructors data in DuckDB or memory"""
        try:
            if not constructors:
                return True
                
            if self.connection:
                import pandas as pd
                df = pd.DataFrame(constructors)
                self.connection.execute("""
                    INSERT OR REPLACE INTO constructors (constructor_id, constructor_name, nationality)
                    SELECT constructor_id, constructor_name, nationality FROM df
                """, {"df": df})
            else:
                # Store in memory
                self.in_memory_data["constructors"] = constructors
            
            logger.info(f"✅ Stored {len(constructors)} constructors")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error storing constructors: {str(e)}")
            return False
    
    async def store_races(self, races: List[Dict]) -> bool:
        """Store races data in DuckDB or memory"""
        try:
            if not races:
                return True
                
            if self.connection:
                import pandas as pd
                df = pd.DataFrame(races)
                self.connection.execute("""
                    INSERT OR REPLACE INTO races (race_id, year, round, gp, date, circuit_name, country)
                    SELECT race_id, year, round, gp, date, circuit_name, country FROM df
                """, {"df": df})
            else:
                # Store in memory
                self.in_memory_data["races"] = races
            
            logger.info(f"✅ Stored {len(races)} races")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error storing races: {str(e)}")
            return False
    
    async def store_race_results(self, race_id: str, results: List[Dict]) -> bool:
        """Store race results in DuckDB or memory"""
        try:
            if not results:
                return True
                
            if self.connection:
                import pandas as pd
                for result in results:
                    result['race_id'] = race_id
                df = pd.DataFrame(results)
                self.connection.execute("""
                    INSERT OR REPLACE INTO race_results 
                    (race_id, position, driver_id, constructor_id, points, time, fastest_lap, fastest_lap_time, status)
                    SELECT race_id, position, driver_id, constructor_id, points, time, fastest_lap, fastest_lap_time, status FROM df
                """, {"df": df})
            else:
                # Store in memory
                self.in_memory_data["race_results"][race_id] = results
            
            logger.info(f"✅ Stored {len(results)} race results for {race_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error storing race results: {str(e)}")
            return False
    
    async def store_laps(self, race_id: str, laps: List[Dict]) -> bool:
        """Store lap data in DuckDB or memory"""
        try:
            if not laps:
                return True
                
            if self.connection:
                import pandas as pd
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
            else:
                # Store in memory
                self.in_memory_data["laps"][race_id] = laps
            
            logger.info(f"✅ Stored {len(laps)} laps for {race_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error storing laps: {str(e)}")
            return False
