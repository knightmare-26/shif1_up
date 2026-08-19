"""
Supabase F1 Service — drop-in replacement for SimpleDuckDBService.
Uses asyncpg + PostgreSQL (Supabase) instead of DuckDB for F1 historical data.
Same public interface as SimpleDuckDBService so all callers work unchanged.
"""

import logging
from typing import Any, Dict, List, Optional

import asyncpg

logger = logging.getLogger(__name__)

BACKEND = "postgres"


class SupabaseF1Service:
    backend = BACKEND

    def __init__(self, database_url: str):
        self.database_url = database_url
        self.pool: Optional[asyncpg.Pool] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self):
        self.pool = await asyncpg.create_pool(
            self.database_url,
            ssl="require",
            min_size=1,
            max_size=5,
        )
        await self._create_tables()
        logger.info("✅ Supabase F1 service connected")

    async def cleanup(self):
        if self.pool:
            await self.pool.close()

    async def _create_tables(self):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS drivers (
                    driver_id   TEXT PRIMARY KEY,
                    full_name   TEXT NOT NULL,
                    nationality TEXT,
                    number      INTEGER,
                    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS constructors (
                    constructor_id   TEXT PRIMARY KEY,
                    constructor_name TEXT NOT NULL,
                    nationality      TEXT,
                    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS races (
                    race_id      TEXT PRIMARY KEY,
                    year         INTEGER NOT NULL,
                    round        INTEGER NOT NULL,
                    gp           TEXT NOT NULL,
                    date         TEXT,
                    circuit_name TEXT,
                    country      TEXT,
                    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS race_results (
                    race_id          TEXT    NOT NULL,
                    position         INTEGER NOT NULL,
                    driver_id        TEXT,
                    constructor_id   TEXT,
                    grid             INTEGER,
                    points           FLOAT,
                    time             TEXT,
                    fastest_lap      BOOLEAN,
                    fastest_lap_time TEXT,
                    status           TEXT,
                    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (race_id, position)
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS laps (
                    race_id      TEXT    NOT NULL,
                    driver_id    TEXT    NOT NULL,
                    lap_number   INTEGER NOT NULL,
                    lap_time_ms  INTEGER,
                    sector1_ms   INTEGER,
                    sector2_ms   INTEGER,
                    sector3_ms   INTEGER,
                    tyre         TEXT,
                    pit          BOOLEAN,
                    position     INTEGER,
                    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (race_id, driver_id, lap_number)
                )
            """)
        logger.info("✅ Supabase F1 tables ready")

    # ------------------------------------------------------------------
    # Raw query — used by PredictionService and health probe
    # ------------------------------------------------------------------

    async def _run_query(self, query: str, params: tuple = None) -> List[Dict]:
        if not self.pool:
            return []
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, *params) if params else await conn.fetch(query)
                return [dict(row) for row in rows]
        except Exception as exc:
            logger.error("❌ Query failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Read methods
    # ------------------------------------------------------------------

    async def get_drivers_by_year(self, year: int) -> List[Dict]:
        return await self._run_query("""
            SELECT DISTINCT d.driver_id, d.full_name, d.nationality, d.number
            FROM drivers d
            JOIN race_results rr ON d.driver_id = rr.driver_id
            JOIN races r         ON rr.race_id   = r.race_id
            WHERE r.year = $1
            ORDER BY d.full_name
        """, (year,))

    async def get_all_drivers(self) -> List[Dict]:
        return await self._run_query(
            "SELECT driver_id, full_name, nationality, number FROM drivers ORDER BY full_name"
        )

    async def get_driver_details(self, driver_id: str, year: int) -> Optional[Dict]:
        rows = await self._run_query("""
            SELECT d.driver_id, d.full_name, d.nationality, d.number,
                   COUNT(rr.race_id)                             AS races_entered,
                   SUM(rr.points)                                AS total_points,
                   COUNT(CASE WHEN rr.position = 1 THEN 1 END)  AS wins
            FROM drivers d
            LEFT JOIN race_results rr ON d.driver_id = rr.driver_id
            LEFT JOIN races r         ON rr.race_id  = r.race_id AND r.year = $1
            WHERE d.driver_id = $2
            GROUP BY d.driver_id, d.full_name, d.nationality, d.number
        """, (year, driver_id))
        return rows[0] if rows else None

    async def get_races_by_year(self, year: int) -> List[Dict]:
        return await self._run_query("""
            SELECT race_id, year, round, gp, date, circuit_name, country
            FROM races WHERE year = $1 ORDER BY round
        """, (year,))

    async def get_race_results(self, race_id: str) -> List[Dict]:
        return await self._run_query("""
            SELECT rr.position, rr.driver_id, d.full_name AS driver_name,
                   d.number AS driver_number, d.nationality AS country_code,
                   rr.constructor_id, c.constructor_name,
                   rr.grid, rr.points, rr.time, rr.fastest_lap, rr.fastest_lap_time, rr.status
            FROM race_results rr
            LEFT JOIN drivers      d ON rr.driver_id      = d.driver_id
            LEFT JOIN constructors c ON rr.constructor_id = c.constructor_id
            WHERE rr.race_id = $1
            ORDER BY rr.position
        """, (race_id,))

    async def get_race_laps(self, race_id: str, driver: Optional[str] = None) -> List[Dict]:
        if driver:
            return await self._run_query("""
                SELECT l.lap_number, l.lap_time_ms, l.sector1_ms, l.sector2_ms,
                       l.sector3_ms, l.tyre, l.pit, l.position, d.full_name AS driver_name
                FROM laps l
                LEFT JOIN drivers d ON l.driver_id = d.driver_id
                WHERE l.race_id = $1 AND l.driver_id = $2
                ORDER BY l.lap_number
            """, (race_id, driver))
        return await self._run_query("""
            SELECT l.lap_number, l.lap_time_ms, l.sector1_ms, l.sector2_ms,
                   l.sector3_ms, l.tyre, l.pit, l.position, d.full_name AS driver_name
            FROM laps l
            LEFT JOIN drivers d ON l.driver_id = d.driver_id
            WHERE l.race_id = $1
            ORDER BY l.lap_number, l.position
        """, (race_id,))

    # ------------------------------------------------------------------
    # Write methods (UPSERT — safe to re-run ingest)
    # ------------------------------------------------------------------

    async def store_drivers(self, drivers: List[Dict]) -> bool:
        if not drivers or not self.pool:
            return True
        try:
            async with self.pool.acquire() as conn:
                await conn.executemany(
                    """INSERT INTO drivers (driver_id, full_name, nationality, number)
                       VALUES ($1, $2, $3, $4)
                       ON CONFLICT (driver_id) DO UPDATE SET
                           full_name   = EXCLUDED.full_name,
                           nationality = EXCLUDED.nationality,
                           number      = EXCLUDED.number""",
                    [(d["driver_id"], d["full_name"], d.get("nationality"), d.get("number"))
                     for d in drivers],
                )
            logger.info("✅ Stored %d drivers", len(drivers))
            return True
        except Exception as exc:
            logger.error("❌ Error storing drivers: %s", exc)
            return False

    async def store_constructors(self, constructors: List[Dict]) -> bool:
        if not constructors or not self.pool:
            return True
        try:
            async with self.pool.acquire() as conn:
                await conn.executemany(
                    """INSERT INTO constructors (constructor_id, constructor_name, nationality)
                       VALUES ($1, $2, $3)
                       ON CONFLICT (constructor_id) DO UPDATE SET
                           constructor_name = EXCLUDED.constructor_name,
                           nationality      = EXCLUDED.nationality""",
                    [(c["constructor_id"], c["constructor_name"], c.get("nationality"))
                     for c in constructors],
                )
            logger.info("✅ Stored %d constructors", len(constructors))
            return True
        except Exception as exc:
            logger.error("❌ Error storing constructors: %s", exc)
            return False

    async def store_races(self, races: List[Dict]) -> bool:
        if not races or not self.pool:
            return True
        try:
            async with self.pool.acquire() as conn:
                await conn.executemany(
                    """INSERT INTO races (race_id, year, round, gp, date, circuit_name, country)
                       VALUES ($1, $2, $3, $4, $5, $6, $7)
                       ON CONFLICT (race_id) DO UPDATE SET
                           year         = EXCLUDED.year,
                           round        = EXCLUDED.round,
                           gp           = EXCLUDED.gp,
                           date         = EXCLUDED.date,
                           circuit_name = EXCLUDED.circuit_name,
                           country      = EXCLUDED.country""",
                    [(r["race_id"], r["year"], r["round"], r["gp"],
                      r.get("date"), r.get("circuit_name"), r.get("country"))
                     for r in races],
                )
            logger.info("✅ Stored %d races", len(races))
            return True
        except Exception as exc:
            logger.error("❌ Error storing races: %s", exc)
            return False

    async def store_race_results(self, race_id: str, results: List[Dict]) -> bool:
        if not results or not self.pool:
            return True
        try:
            async with self.pool.acquire() as conn:
                await conn.executemany(
                    """INSERT INTO race_results
                           (race_id, position, driver_id, constructor_id, grid, points,
                            time, fastest_lap, fastest_lap_time, status)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                       ON CONFLICT (race_id, position) DO UPDATE SET
                           driver_id        = EXCLUDED.driver_id,
                           constructor_id   = EXCLUDED.constructor_id,
                           grid             = EXCLUDED.grid,
                           points           = EXCLUDED.points,
                           time             = EXCLUDED.time,
                           fastest_lap      = EXCLUDED.fastest_lap,
                           fastest_lap_time = EXCLUDED.fastest_lap_time,
                           status           = EXCLUDED.status""",
                    [(race_id, r["position"], r["driver_id"], r.get("constructor_id"),
                      r.get("grid"), r.get("points"), r.get("time"), r.get("fastest_lap"),
                      r.get("fastest_lap_time"), r.get("status"))
                     for r in results],
                )
            logger.info("✅ Stored %d race results for %s", len(results), race_id)
            return True
        except Exception as exc:
            logger.error("❌ Error storing race results: %s", exc)
            return False

    async def store_laps(self, race_id: str, laps: List[Dict]) -> bool:
        if not laps or not self.pool:
            return True
        try:
            async with self.pool.acquire() as conn:
                await conn.executemany(
                    """INSERT INTO laps
                           (race_id, driver_id, lap_number, lap_time_ms, sector1_ms, sector2_ms,
                            sector3_ms, tyre, pit, position)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                       ON CONFLICT (race_id, driver_id, lap_number) DO UPDATE SET
                           lap_time_ms = EXCLUDED.lap_time_ms,
                           sector1_ms  = EXCLUDED.sector1_ms,
                           sector2_ms  = EXCLUDED.sector2_ms,
                           sector3_ms  = EXCLUDED.sector3_ms,
                           tyre        = EXCLUDED.tyre,
                           pit         = EXCLUDED.pit,
                           position    = EXCLUDED.position""",
                    [(race_id, l["driver_id"], l["lap_number"], l.get("lap_time_ms"),
                      l.get("sector1_ms"), l.get("sector2_ms"), l.get("sector3_ms"),
                      l.get("tyre"), l.get("pit"), l.get("position"))
                     for l in laps],
                )
            logger.info("✅ Stored %d laps for %s", len(laps), race_id)
            return True
        except Exception as exc:
            logger.error("❌ Error storing laps: %s", exc)
            return False
