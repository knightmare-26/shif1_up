"""
Working Enhanced FastAPI Backend for Shif1 UP - Advanced F1 Analytics Platform
Features: DuckDB + Parquet storage, Redis live state, WebSocket streaming
"""

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
import asyncio
import json
import os
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
import pandas as pd
from contextlib import asynccontextmanager

# Import our services
from services.simple_duckdb_service import SimpleDuckDBService
from services.mock_redis_service import MockRedisService
from services.fastf1_service import FastF1Service
from services.ergast_service import ErgastService
from services.cache_service import CacheService

# Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
DUCKDB_PATH = os.getenv("DUCKDB_PATH", "data/f1_history.duckdb")
FASTF1_CACHE_DIR = os.getenv("FASTF1_CACHE_DIR", "data/fastf1_cache")

# Global services
redis_service = None
duckdb_service = None
fastf1_service = None
ergast_service = None
cache_service = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global redis_service, duckdb_service, fastf1_service, ergast_service, cache_service
    
    # Initialize services
    logger.info("🚀 Starting Shif1 UP Working Enhanced API...")
    
    # Initialize Redis service (mock if Redis not available)
    try:
        redis_service = MockRedisService(REDIS_URL)
        await redis_service.initialize()
        logger.info("✅ Redis service initialized (mock mode)")
    except Exception as e:
        logger.warning(f"⚠️ Redis initialization failed: {str(e)}, using mock service")
        redis_service = MockRedisService(REDIS_URL)
        await redis_service.initialize()
    
    # Initialize DuckDB service
    duckdb_service = SimpleDuckDBService(DUCKDB_PATH)
    await duckdb_service.initialize()
    
    # Initialize other services
    fastf1_service = FastF1Service()
    ergast_service = ErgastService()
    cache_service = CacheService()
    await cache_service.initialize()
    
    # Load sample data
    await load_sample_data()
    
    logger.info("✅ All services initialized successfully")
    
    yield
    
    # Cleanup
    logger.info("🛑 Shutting down Shif1 UP Working Enhanced API...")
    if redis_service:
        await redis_service.cleanup()
    if duckdb_service:
        await duckdb_service.cleanup()
    if cache_service:
        await cache_service.cleanup()

# Initialize FastAPI app
app = FastAPI(
    title="Shif1 UP Working Enhanced API",
    description="Advanced F1 Analytics Platform with DuckDB, Redis, and WebSocket streaming",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Years where FastF1 has complete data
FASTF1_YEARS = [2020, 2021, 2022, 2023]

async def load_sample_data():
    """Load sample data into DuckDB/memory"""
    try:
        # Sample drivers
        sample_drivers = [
            {
                "driver_id": "verstappen",
                "full_name": "Max Verstappen",
                "nationality": "Dutch",
                "number": 1
            },
            {
                "driver_id": "norris",
                "full_name": "Lando Norris",
                "nationality": "British",
                "number": 4
            },
            {
                "driver_id": "leclerc",
                "full_name": "Charles Leclerc",
                "nationality": "Monegasque",
                "number": 16
            },
            {
                "driver_id": "piastri",
                "full_name": "Oscar Piastri",
                "nationality": "Australian",
                "number": 81
            },
            {
                "driver_id": "sainz",
                "full_name": "Carlos Sainz",
                "nationality": "Spanish",
                "number": 55
            }
        ]
        
        # Sample constructors
        sample_constructors = [
            {
                "constructor_id": "red_bull_racing",
                "constructor_name": "Red Bull Racing Honda RBPT",
                "nationality": "Austrian"
            },
            {
                "constructor_id": "mclaren",
                "constructor_name": "McLaren Mercedes",
                "nationality": "British"
            },
            {
                "constructor_id": "ferrari",
                "constructor_name": "Ferrari",
                "nationality": "Italian"
            }
        ]
        
        # Sample races
        sample_races = [
            {
                "race_id": "2024_Bahrain",
                "year": 2024,
                "round": 1,
                "gp": "Bahrain",
                "date": "2024-03-02",
                "circuit_name": "Bahrain International Circuit",
                "country": "Bahrain"
            },
            {
                "race_id": "2024_Saudi_Arabia",
                "year": 2024,
                "round": 2,
                "gp": "Saudi Arabia",
                "date": "2024-03-09",
                "circuit_name": "Jeddah Corniche Circuit",
                "country": "Saudi Arabia"
            }
        ]
        
        # Sample race results
        sample_results = [
            {
                "position": 1,
                "driver_id": "verstappen",
                "constructor_id": "red_bull_racing",
                "points": 25,
                "time": "1:31:44.742",
                "fastest_lap": True,
                "fastest_lap_time": "1:33.660",
                "status": "Finished"
            },
            {
                "position": 2,
                "driver_id": "norris",
                "constructor_id": "mclaren",
                "points": 18,
                "time": "+22.457",
                "fastest_lap": False,
                "fastest_lap_time": None,
                "status": "Finished"
            }
        ]
        
        # Store sample data
        await duckdb_service.store_drivers(sample_drivers)
        await duckdb_service.store_constructors(sample_constructors)
        await duckdb_service.store_races(sample_races)
        await duckdb_service.store_race_results("2024_Bahrain", sample_results)
        
        logger.info("✅ Sample data loaded successfully")
        
    except Exception as e:
        logger.error(f"❌ Error loading sample data: {str(e)}")

# ============================================================================
# HEALTH CHECK ENDPOINTS
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    redis_info = await redis_service.get_redis_info() if redis_service else {}
    
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "Shif1 UP Working Enhanced API",
        "version": "2.0.0",
        "redis": redis_info,
        "duckdb": "connected" if duckdb_service else "not available"
    }

# ============================================================================
# DRIVER ENDPOINTS
# ============================================================================

@app.get("/drivers")
async def get_drivers(year: Optional[int] = None):
    """Get list of drivers; if year provided filter drivers who raced that year"""
    try:
        if year:
            # Query DuckDB for drivers who raced in the specified year
            drivers = await duckdb_service.get_drivers_by_year(year)
            if not drivers:
                # Fallback to API if no data in DuckDB
                if year in FASTF1_YEARS:
                    drivers = await fastf1_service.get_driver_standings(year)
                else:
                    async with ergast_service as ergast:
                        drivers = await ergast.get_driver_standings(year)
        else:
            # Get all drivers from DuckDB
            drivers = await duckdb_service.get_all_drivers()
            
        return drivers
        
    except Exception as e:
        logger.error(f"❌ Error fetching drivers: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch drivers: {str(e)}")

@app.get("/drivers/{driver_id}")
async def get_driver_details(driver_id: str, year: Optional[int] = None):
    """Get detailed information about a specific driver"""
    try:
        if year is None:
            year = datetime.now().year
            
        driver_data = await duckdb_service.get_driver_details(driver_id, year)
        if not driver_data:
            # Fallback to FastF1 service
            driver_data = await fastf1_service.get_driver_details(driver_id, year)
            
        return driver_data
        
    except Exception as e:
        logger.error(f"❌ Error fetching driver details: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch driver details: {str(e)}")

# ============================================================================
# RACE ENDPOINTS
# ============================================================================

@app.get("/races")
async def get_races(year: Optional[int] = None):
    """Get list of races for a year"""
    try:
        if year is None:
            year = datetime.now().year
            
        races = await duckdb_service.get_races_by_year(year)
        if not races:
            # Fallback to API
            if year in FASTF1_YEARS:
                races = await fastf1_service.get_race_schedule(year)
            else:
                async with ergast_service as ergast:
                    races = await ergast.get_race_schedule(year)
                    
        return races
        
    except Exception as e:
        logger.error(f"❌ Error fetching races: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch races: {str(e)}")

@app.get("/race/{race_id}/results")
async def get_race_results(race_id: str):
    """Get race classification ordered by position"""
    try:
        results = await duckdb_service.get_race_results(race_id)
        if not results:
            # Fallback to FastF1 service
            year, gp = race_id.split('_', 1)
            results = await fastf1_service.get_race_results(int(year), gp)
            
        return results
        
    except Exception as e:
        logger.error(f"❌ Error fetching race results: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch race results: {str(e)}")

@app.get("/race/{race_id}/laps")
async def get_race_laps(race_id: str, driver: Optional[str] = None):
    """Get laps for the session (or for a given driver)"""
    try:
        laps = await duckdb_service.get_race_laps(race_id, driver)
        if not laps:
            # Fallback to FastF1 service
            year, gp = race_id.split('_', 1)
            laps = await fastf1_service.get_session_laps(int(year), gp, 'R', driver)
            
        return laps
        
    except Exception as e:
        logger.error(f"❌ Error fetching race laps: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch race laps: {str(e)}")

# ============================================================================
# LIVE DATA ENDPOINTS
# ============================================================================

@app.get("/live/{race_id}/state")
async def get_live_state(race_id: str):
    """Get current live state from Redis"""
    try:
        state = await redis_service.get_live_state(race_id)
        if not state:
            # Return mock live state if no data available
            state = {
                "race_id": race_id,
                "timestamp": datetime.utcnow().isoformat(),
                "session_status": "live",
                "current_lap": 15,
                "leader": "VER",
                "positions": [
                    {
                        "driver": "VER",
                        "position": 1,
                        "lap_number": 15,
                        "tyre": "SOFT",
                        "gap": None,
                        "last_lap_time": "1:33.660"
                    },
                    {
                        "driver": "NOR",
                        "position": 2,
                        "lap_number": 15,
                        "tyre": "SOFT",
                        "gap": "+22.457",
                        "last_lap_time": "1:34.120"
                    }
                ],
                "last_updated": datetime.utcnow().isoformat()
            }
        return state
        
    except Exception as e:
        logger.error(f"❌ Error fetching live state: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch live state: {str(e)}")

@app.websocket("/ws/live/{race_id}")
async def websocket_live_updates(websocket: WebSocket, race_id: str):
    """WebSocket endpoint for live race updates"""
    await websocket.accept()
    
    try:
        # Subscribe to Redis channel for this race
        channel = f"race:{race_id}:updates"
        
        # Send initial state if available
        initial_state = await redis_service.get_live_state(race_id)
        if initial_state:
            await websocket.send_text(json.dumps({
                "type": "initial_state",
                "data": initial_state
            }))
        
        # Listen for updates
        async for message in redis_service.subscribe_to_race(race_id):
            try:
                await websocket.send_text(json.dumps({
                    "type": "update",
                    "data": message
                }))
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"❌ Error sending WebSocket message: {str(e)}")
                break
                    
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for race {race_id}")
    except Exception as e:
        logger.error(f"❌ WebSocket error for race {race_id}: {str(e)}")
    finally:
        logger.info(f"WebSocket connection closed for race {race_id}")

# ============================================================================
# LEGACY API ENDPOINTS (for backward compatibility)
# ============================================================================

@app.get("/api/drivers")
async def get_driver_standings_legacy(
    year: int = None,
    round: int = None,
    use_cache: bool = True
):
    """Legacy driver standings endpoint for backward compatibility"""
    try:
        if year is None:
            year = datetime.now().year
            
        cache_key = f"driver_standings_{year}_{round or 'current'}"
        
        if use_cache:
            cached_data = await cache_service.get(cache_key)
            if cached_data:
                logger.info(f"📦 Returning cached driver standings for {year}")
                return cached_data
        
        # Choose data source based on year
        if year in FASTF1_YEARS:
            logger.info(f"🚀 Using FastF1 for {year} (complete session data available)")
            standings = await fastf1_service.get_driver_standings(year, round)
        else:
            logger.info(f"📚 Using Ergast API for {year} (historical data)")
            async with ergast_service as ergast:
                standings = await ergast.get_driver_standings(year, round)
        
        # Cache the results
        await cache_service.set(cache_key, standings, ttl=3600)
        
        logger.info(f"✅ Fetched {len(standings)} driver standings for {year}")
        return standings
        
    except Exception as e:
        logger.error(f"❌ Error fetching driver standings: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch driver standings: {str(e)}")

@app.get("/api/constructors")
async def get_constructor_standings_legacy(
    year: int = None,
    round: int = None,
    use_cache: bool = True
):
    """Legacy constructor standings endpoint for backward compatibility"""
    try:
        if year is None:
            year = datetime.now().year
            
        cache_key = f"constructor_standings_{year}_{round or 'current'}"
        
        if use_cache:
            cached_data = await cache_service.get(cache_key)
            if cached_data:
                logger.info(f"📦 Returning cached constructor standings for {year}")
                return cached_data
        
        # Choose data source based on year
        if year in FASTF1_YEARS:
            logger.info(f"🚀 Using FastF1 for {year} (complete session data available)")
            standings = await fastf1_service.get_constructor_standings(year, round)
        else:
            logger.info(f"📚 Using Ergast API for {year} (historical data)")
            async with ergast_service as ergast:
                standings = await ergast.get_constructor_standings(year, round)
        
        # Cache the results
        await cache_service.set(cache_key, standings, ttl=3600)
        
        logger.info(f"✅ Fetched {len(standings)} constructor standings for {year}")
        return standings
        
    except Exception as e:
        logger.error(f"❌ Error fetching constructor standings: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch constructor standings: {str(e)}")

@app.get("/api/races")
async def get_race_schedule_legacy(
    year: int = None,
    use_cache: bool = True
):
    """Legacy race schedule endpoint for backward compatibility"""
    try:
        if year is None:
            year = datetime.now().year
            
        cache_key = f"race_schedule_{year}"
        
        if use_cache:
            cached_data = await cache_service.get(cache_key)
            if cached_data:
                logger.info(f"📦 Returning cached race schedule for {year}")
                return cached_data
        
        # Choose data source based on year
        if year in FASTF1_YEARS:
            logger.info(f"🚀 Using FastF1 for {year} (complete session data available)")
            schedule = await fastf1_service.get_race_schedule(year)
        else:
            logger.info(f"📚 Using Ergast API for {year} (historical data)")
            async with ergast_service as ergast:
                schedule = await ergast.get_race_schedule(year)
        
        # Cache the results
        await cache_service.set(cache_key, schedule, ttl=7200)  # 2 hour cache
        
        logger.info(f"✅ Fetched {len(schedule)} races for {year}")
        return schedule
        
    except Exception as e:
        logger.error(f"❌ Error fetching race schedule: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch race schedule: {str(e)}")

# ============================================================================
# CACHE MANAGEMENT ENDPOINTS
# ============================================================================

@app.post("/api/cache/clear")
async def clear_cache():
    """Clear all cached data"""
    try:
        await cache_service.clear_all()
        return {"message": "Cache cleared successfully"}
        
    except Exception as e:
        logger.error(f"❌ Error clearing cache: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to clear cache: {str(e)}")

@app.get("/api/cache/stats")
async def get_cache_stats():
    """Get cache statistics"""
    try:
        stats = await cache_service.get_stats()
        return stats
        
    except Exception as e:
        logger.error(f"❌ Error fetching cache stats: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch cache stats: {str(e)}")

# ============================================================================
# LIVE DATA SIMULATION ENDPOINTS
# ============================================================================

@app.post("/simulate/live/{race_id}")
async def simulate_live_data(race_id: str):
    """Simulate live data updates for testing"""
    try:
        # Create mock live state
        live_state = {
            "race_id": race_id,
            "timestamp": datetime.utcnow().isoformat(),
            "session_status": "live",
            "current_lap": 15,
            "leader": "VER",
            "positions": [
                {
                    "driver": "VER",
                    "position": 1,
                    "lap_number": 15,
                    "tyre": "SOFT",
                    "gap": None,
                    "last_lap_time": "1:33.660"
                },
                {
                    "driver": "NOR",
                    "position": 2,
                    "lap_number": 15,
                    "tyre": "SOFT",
                    "gap": "+22.457",
                    "last_lap_time": "1:34.120"
                }
            ],
            "last_updated": datetime.utcnow().isoformat()
        }
        
        # Store live state
        await redis_service.set_live_state(race_id, live_state)
        
        # Publish update
        await redis_service.publish_update(race_id, {
            "type": "state_update",
            "timestamp": datetime.utcnow().isoformat(),
            "state": live_state
        })
        
        return {"message": f"Live data simulation started for {race_id}"}
        
    except Exception as e:
        logger.error(f"❌ Error simulating live data: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to simulate live data: {str(e)}")

if __name__ == "__main__":
    uvicorn.run(
        "working_enhanced_main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
