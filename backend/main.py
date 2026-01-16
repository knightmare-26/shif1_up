"""
FastAPI Backend for Shif1 UP - F1 Analytics Platform
Integrates with FastF1 library for real F1 data
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
import asyncio
from datetime import datetime, timedelta
import logging
from typing import List, Optional, Dict, Any
import pandas as pd

from services.fastf1_service import FastF1Service
from services.ergast_service import ErgastService
from services.cache_service import CacheService
from models.f1_models import (
    DriverStanding, ConstructorStanding, RaceEvent, 
    SessionData, LapData, TelemetryData, WeatherData
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Shif1 UP API",
    description="FastAPI backend for F1 Analytics Platform with FastF1 integration",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
fastf1_service = FastF1Service()
ergast_service = ErgastService()
cache_service = CacheService()

# Years where FastF1 has complete data (recent years with full session data)
FASTF1_YEARS = [2020, 2021, 2022, 2023]  # Add more years as FastF1 data becomes available

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    logger.info("🚀 Starting Shif1 UP API...")
    await cache_service.initialize()
    logger.info("✅ Services initialized successfully")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("🛑 Shutting down Shif1 UP API...")
    await cache_service.cleanup()

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "Shif1 UP API"
    }

# Driver endpoints
@app.get("/api/drivers", response_model=List[DriverStanding])
async def get_driver_standings(
    year: int = None,
    round: int = None,
    use_cache: bool = True
):
    """Get driver standings for a specific year and round"""
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
        await cache_service.set(cache_key, standings, ttl=3600)  # 1 hour cache
        
        logger.info(f"✅ Fetched {len(standings)} driver standings for {year}")
        return standings
        
    except Exception as e:
        logger.error(f"❌ Error fetching driver standings: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch driver standings: {str(e)}")

@app.get("/api/drivers/{driver_id}")
async def get_driver_details(driver_id: str, year: int = None):
    """Get detailed information about a specific driver"""
    try:
        if year is None:
            year = datetime.now().year
            
        driver_data = await fastf1_service.get_driver_details(driver_id, year)
        return driver_data
        
    except Exception as e:
        logger.error(f"❌ Error fetching driver details: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch driver details: {str(e)}")

# Constructor endpoints
@app.get("/api/constructors", response_model=List[ConstructorStanding])
async def get_constructor_standings(
    year: int = None,
    round: int = None,
    use_cache: bool = True
):
    """Get constructor standings for a specific year and round"""
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
        await cache_service.set(cache_key, standings, ttl=3600)
        
        logger.info(f"✅ Fetched {len(standings)} constructor standings for {year}")
        return standings
        
    except Exception as e:
        logger.error(f"❌ Error fetching constructor standings: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch constructor standings: {str(e)}")

# Race events endpoints
@app.get("/api/races", response_model=List[RaceEvent])
async def get_race_schedule(
    year: int = None,
    use_cache: bool = True
):
    """Get race schedule for a specific year"""
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
        await cache_service.set(cache_key, schedule, ttl=7200)  # 2 hour cache
        
        logger.info(f"✅ Fetched {len(schedule)} races for {year}")
        return schedule
        
    except Exception as e:
        logger.error(f"❌ Error fetching race schedule: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch race schedule: {str(e)}")

@app.get("/api/races/{race_id}")
async def get_race_details(race_id: str, year: int = None):
    """Get detailed information about a specific race"""
    try:
        if year is None:
            year = datetime.now().year
            
        race_data = await fastf1_service.get_race_details(race_id, year)
        return race_data
        
    except Exception as e:
        logger.error(f"❌ Error fetching race details: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch race details: {str(e)}")

# Session data endpoints
@app.get("/api/sessions/{session_id}")
async def get_session_data(
    session_id: str,
    year: int = None,
    include_telemetry: bool = False
):
    """Get session data (practice, qualifying, race)"""
    try:
        if year is None:
            year = datetime.now().year
            
        session_data = await fastf1_service.get_session_data(
            session_id, year, include_telemetry
        )
        return session_data
        
    except Exception as e:
        logger.error(f"❌ Error fetching session data: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch session data: {str(e)}")

# Live data endpoints
@app.get("/api/live/session")
async def get_live_session_data():
    """Get current live session data"""
    try:
        live_data = await fastf1_service.get_live_session_data()
        return live_data
        
    except Exception as e:
        logger.error(f"❌ Error fetching live session data: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch live session data: {str(e)}")

@app.get("/api/live/positions")
async def get_live_positions():
    """Get current live driver positions"""
    try:
        positions = await fastf1_service.get_live_positions()
        return positions
        
    except Exception as e:
        logger.error(f"❌ Error fetching live positions: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch live positions: {str(e)}")

# Telemetry endpoints
@app.get("/api/telemetry/{session_id}/{driver_id}")
async def get_driver_telemetry(
    session_id: str,
    driver_id: str,
    year: int = None,
    lap: int = None
):
    """Get telemetry data for a specific driver and session"""
    try:
        if year is None:
            year = datetime.now().year
            
        telemetry = await fastf1_service.get_driver_telemetry(
            session_id, driver_id, year, lap
        )
        return telemetry
        
    except Exception as e:
        logger.error(f"❌ Error fetching telemetry: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch telemetry: {str(e)}")

# Weather endpoints
@app.get("/api/weather/{session_id}")
async def get_session_weather(session_id: str, year: int = None):
    """Get weather data for a specific session"""
    try:
        if year is None:
            year = datetime.now().year
            
        weather = await fastf1_service.get_session_weather(session_id, year)
        return weather
        
    except Exception as e:
        logger.error(f"❌ Error fetching weather data: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch weather data: {str(e)}")

# Cache management endpoints
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

# Background data refresh
@app.post("/api/refresh/{data_type}")
async def refresh_data(data_type: str, background_tasks: BackgroundTasks):
    """Trigger background refresh of specific data type"""
    try:
        background_tasks.add_task(fastf1_service.refresh_data, data_type)
        return {"message": f"Background refresh started for {data_type}"}
        
    except Exception as e:
        logger.error(f"❌ Error starting background refresh: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to start background refresh: {str(e)}")

# New FastF1 API endpoints following the example pattern
@app.get("/race/{year}/{gp}/results")
async def get_race_results(year: int, gp: str):
    """Return the session.results for the Race (session 'R').
    Example: /race/2024/Bahrain/results
    """
    try:
        results = await fastf1_service.get_race_results(year, gp)
        if "error" in results:
            raise HTTPException(status_code=404, detail=results["error"])
        return results
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error fetching race results: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch race results: {str(e)}")

@app.get("/race/{year}/{gp}/{session}/laps")
async def get_session_laps(year: int, gp: str, session: str, driver: Optional[str] = None):
    """Return laps for a session. session can be 'P1','P2','Q','R' etc.
    Optional query param driver (driver code e.g. 'VER') to filter by driver.
    Example: /race/2024/Bahrain/R/laps?driver=VER
    """
    try:
        laps = await fastf1_service.get_session_laps(year, gp, session, driver)
        if "error" in laps:
            raise HTTPException(status_code=404, detail=laps["error"])
        return laps
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error fetching session laps: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch session laps: {str(e)}")

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
