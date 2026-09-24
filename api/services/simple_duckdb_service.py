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
            "telemetry_files": [],
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
            
            # Race results table — session_type distinguishes the main race
            # from a sprint race on the same weekend (same race_id, separate
            # results), so the primary key includes it.
            self.connection.execute("""
                CREATE TABLE IF NOT EXISTS race_results (
                    race_id VARCHAR NOT NULL,
                    session_type VARCHAR NOT NULL DEFAULT 'race',
                    position INTEGER NOT NULL,
                    driver_id VARCHAR,
                    constructor_id VARCHAR,
                    grid INTEGER,
                    points FLOAT,
                    time VARCHAR,
                    fastest_lap BOOLEAN,
                    fastest_lap_time VARCHAR,
                    status VARCHAR,
                    laps_completed INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (race_id, session_type, position)
                )
            """)

            # Laps table
            self.connection.execute("""
                CREATE TABLE IF NOT EXISTS laps (
                    race_id VARCHAR NOT NULL,
                    driver_id VARCHAR NOT NULL,
                    lap_number INTEGER NOT NULL,
                    lap_time_ms INTEGER,
                    sector1_ms INTEGER,
                    sector2_ms INTEGER,
                    sector3_ms INTEGER,
                    tyre VARCHAR,
                    pit BOOLEAN,
                    position INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (race_id, driver_id, lap_number)
                )
            """)

            # Prediction cache table — first live prediction for a circuit is
            # computed from the model, then cached here keyed to the model
            # that produced it so a retrain naturally invalidates old rows.
            self.connection.execute("""
                CREATE TABLE IF NOT EXISTS prediction_cache (
                    circuit_name VARCHAR NOT NULL,
                    session_type VARCHAR NOT NULL,
                    model_trained_at VARCHAR,
                    result_json VARCHAR NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (circuit_name, session_type)
                )
            """)

            # Migrate: add grid column if missing (added in Phase 5)
            existing = [
                r[0] for r in self.connection.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_name='race_results'"
                ).fetchall()
            ]
            if "grid" not in existing:
                self.connection.execute("ALTER TABLE race_results ADD COLUMN grid INTEGER")
                logger.info("✅ Migrated race_results: added grid column")

            # Migrate: add session_type + widen the primary key to include it,
            # so a sprint race's results (same race_id) don't collide with the
            # main race's. DuckDB can't ALTER a primary key in place, so the
            # table is rebuilt with existing rows tagged as 'race'.
            if "session_type" not in existing:
                self.connection.execute("ALTER TABLE race_results ADD COLUMN session_type VARCHAR DEFAULT 'race'")
                self.connection.execute("UPDATE race_results SET session_type = 'race' WHERE session_type IS NULL")
                self.connection.execute("""
                    CREATE TABLE race_results_new (
                        race_id VARCHAR NOT NULL,
                        session_type VARCHAR NOT NULL DEFAULT 'race',
                        position INTEGER NOT NULL,
                        driver_id VARCHAR,
                        constructor_id VARCHAR,
                        grid INTEGER,
                        points FLOAT,
                        time VARCHAR,
                        fastest_lap BOOLEAN,
                        fastest_lap_time VARCHAR,
                        status VARCHAR,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (race_id, session_type, position)
                    )
                """)
                self.connection.execute("""
                    INSERT INTO race_results_new
                    SELECT race_id, session_type, position, driver_id, constructor_id, grid,
                           points, time, fastest_lap, fastest_lap_time, status, created_at
                    FROM race_results
                """)
                self.connection.execute("DROP TABLE race_results")
                self.connection.execute("ALTER TABLE race_results_new RENAME TO race_results")
                logger.info("✅ Migrated race_results: added session_type, widened primary key")

            # Migrate: add laps_completed if missing (re-check columns — the
            # session_type migration above may have just rebuilt the table)
            existing = [
                r[0] for r in self.connection.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_name='race_results'"
                ).fetchall()
            ]
            if "laps_completed" not in existing:
                self.connection.execute("ALTER TABLE race_results ADD COLUMN laps_completed INTEGER")
                logger.info("✅ Migrated race_results: added laps_completed column")

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
    
    async def get_driver_result_counts(self, year: int) -> List[Dict]:
        """Race and sprint wins/podiums per driver for one season (see DRIVER_RESULT_COUNTS_SQL)."""
        from services.supabase_f1_service import DRIVER_RESULT_COUNTS_SQL
        try:
            return await self._run_query(DRIVER_RESULT_COUNTS_SQL.format(year="?"), (year,))
        except Exception as e:
            logger.error(f"❌ Error counting driver results: {str(e)}")
            return []

    async def get_race_results(self, race_id: str, session_type: str = "race") -> List[Dict]:
        """Get race results for a specific race (main race by default; pass
        session_type='sprint' for that weekend's sprint results)."""
        try:
            if self.connection:
                query = """
                    SELECT rr.position, rr.driver_id, d.full_name as driver_name,
                           d.number as driver_number, d.nationality as country_code,
                           rr.constructor_id, c.constructor_name,
                           rr.grid, rr.points, rr.time, rr.fastest_lap, rr.fastest_lap_time, rr.status,
                           rr.laps_completed
                    FROM race_results rr
                    LEFT JOIN drivers d ON rr.driver_id = d.driver_id
                    LEFT JOIN constructors c ON rr.constructor_id = c.constructor_id
                    WHERE rr.race_id = ? AND rr.session_type = ?
                    ORDER BY rr.position
                """
                return await self._run_query(query, (race_id, session_type))
            else:
                # Fallback to in-memory data
                return self.in_memory_data["race_results"].get(f"{race_id}:{session_type}", [])
                
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
                self.connection.executemany(
                    "INSERT OR REPLACE INTO drivers (driver_id, full_name, nationality, number) VALUES (?, ?, ?, ?)",
                    [(d["driver_id"], d["full_name"], d.get("nationality"), d.get("number")) for d in drivers],
                )
            else:
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
                self.connection.executemany(
                    "INSERT OR REPLACE INTO constructors (constructor_id, constructor_name, nationality) VALUES (?, ?, ?)",
                    [(c["constructor_id"], c["constructor_name"], c.get("nationality")) for c in constructors],
                )
            else:
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
                self.connection.executemany(
                    "INSERT OR REPLACE INTO races (race_id, year, round, gp, date, circuit_name, country) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [(r["race_id"], r["year"], r["round"], r["gp"], r.get("date"), r.get("circuit_name"), r.get("country")) for r in races],
                )
            else:
                self.in_memory_data["races"] = races

            logger.info(f"✅ Stored {len(races)} races")
            return True

        except Exception as e:
            logger.error(f"❌ Error storing races: {str(e)}")
            return False
    
    async def store_race_results(self, race_id: str, results: List[Dict], session_type: str = "race") -> bool:
        """Store race results in DuckDB or memory. `session_type` is 'race' or
        'sprint' — a sprint's results share the race_id but never collide
        with the main race's since the primary key includes session_type."""
        try:
            if not results:
                return True

            if self.connection:
                self.connection.executemany(
                    """INSERT OR REPLACE INTO race_results
                       (race_id, session_type, position, driver_id, constructor_id, grid, points, time, fastest_lap, fastest_lap_time, status, laps_completed)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    [(race_id, session_type, r["position"], r["driver_id"], r.get("constructor_id"),
                      r.get("grid"), r.get("points"), r.get("time"), r.get("fastest_lap"),
                      r.get("fastest_lap_time"), r.get("status"), r.get("laps_completed")) for r in results],
                )
            else:
                self.in_memory_data["race_results"][f"{race_id}:{session_type}"] = results

            logger.info(f"✅ Stored {len(results)} {session_type} results for {race_id}")
            return True

        except Exception as e:
            logger.error(f"❌ Error storing race results: {str(e)}")
            return False
    
    async def get_prediction_cache(self, circuit_name: str, session_type: str) -> Optional[Dict]:
        """Fetch a cached prediction result, if one exists for this circuit/session."""
        try:
            if not self.connection:
                return None
            rows = await self._run_query(
                "SELECT model_trained_at, result_json FROM prediction_cache "
                "WHERE circuit_name = ? AND session_type = ?",
                (circuit_name, session_type),
            )
            if not rows:
                return None
            return {"model_trained_at": rows[0]["model_trained_at"], "result": json.loads(rows[0]["result_json"])}
        except Exception as e:
            logger.error(f"❌ Error reading prediction cache: {str(e)}")
            return None

    async def set_prediction_cache(self, circuit_name: str, session_type: str,
                                    model_trained_at: str, result: Dict) -> bool:
        """Cache a computed prediction result for a circuit/session."""
        try:
            if not self.connection:
                return True
            self.connection.execute(
                "INSERT OR REPLACE INTO prediction_cache "
                "(circuit_name, session_type, model_trained_at, result_json) VALUES (?, ?, ?, ?)",
                (circuit_name, session_type, model_trained_at, json.dumps(result)),
            )
            return True
        except Exception as e:
            logger.error(f"❌ Error writing prediction cache: {str(e)}")
            return False

    async def clear_prediction_cache(self) -> bool:
        """Drop cached per-circuit predictions — called after a retrain since old
        cached output no longer reflects the current model. The walk-forward
        backtest row is kept: it's expensive, evaluates held-out seasons rather
        than the live model, and is keyed to the training data, not the model."""
        try:
            if self.connection:
                self.connection.execute("DELETE FROM prediction_cache WHERE circuit_name <> '_walkforward'")
            return True
        except Exception as e:
            logger.error(f"❌ Error clearing prediction cache: {str(e)}")
            return False

    async def store_laps(self, race_id: str, laps: List[Dict]) -> bool:
        """Store lap data in DuckDB or memory"""
        try:
            if not laps:
                return True

            if self.connection:
                self.connection.executemany(
                    """INSERT OR REPLACE INTO laps
                       (race_id, driver_id, lap_number, lap_time_ms, sector1_ms, sector2_ms,
                        sector3_ms, tyre, pit, position)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    [(race_id, l["driver_id"], l["lap_number"], l.get("lap_time_ms"),
                      l.get("sector1_ms"), l.get("sector2_ms"), l.get("sector3_ms"),
                      l.get("tyre"), l.get("pit"), l.get("position")) for l in laps],
                )
            else:
                self.in_memory_data["laps"][race_id] = laps

            logger.info(f"✅ Stored {len(laps)} laps for {race_id}")
            return True

        except Exception as e:
            logger.error(f"❌ Error storing laps: {str(e)}")
            return False
