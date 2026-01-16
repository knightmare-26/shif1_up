"""
Simplified FastAPI Backend for Shif1 UP - F1 Analytics Platform
Runs without Redis for basic testing
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
import asyncio
from datetime import datetime
from typing import List, Optional, Dict, Any
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Shif1 UP Simple API",
    description="Simplified F1 Analytics Platform for testing",
    version="2.0.0",
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

# ============================================================================
# HEALTH CHECK ENDPOINTS
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "Shif1 UP Simple API",
        "version": "2.0.0"
    }

# ============================================================================
# DRIVER ENDPOINTS
# ============================================================================

@app.get("/drivers")
async def get_drivers(year: Optional[int] = None):
    """Get list of drivers; if year provided filter drivers who raced that year"""
    try:
        # Sample data for testing
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
        
        if year:
            logger.info(f"📊 Returning drivers for year {year}")
        else:
            logger.info("📊 Returning all drivers")
            
        return sample_drivers
        
    except Exception as e:
        logger.error(f"❌ Error fetching drivers: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch drivers: {str(e)}")

@app.get("/drivers/{driver_id}")
async def get_driver_details(driver_id: str, year: Optional[int] = None):
    """Get detailed information about a specific driver"""
    try:
        # Sample driver details
        driver_details = {
            "driver_id": driver_id,
            "full_name": f"Driver {driver_id.title()}",
            "nationality": "Unknown",
            "number": 0,
            "races_entered": 0,
            "total_points": 0,
            "wins": 0
        }
        
        logger.info(f"📊 Returning driver details for {driver_id}")
        return driver_details
        
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
        # Sample race data
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
            },
            {
                "race_id": "2024_Australia",
                "year": 2024,
                "round": 3,
                "gp": "Australia",
                "date": "2024-03-24",
                "circuit_name": "Albert Park Circuit",
                "country": "Australia"
            }
        ]
        
        if year:
            filtered_races = [race for race in sample_races if race["year"] == year]
            logger.info(f"📊 Returning {len(filtered_races)} races for year {year}")
            return filtered_races
        else:
            logger.info(f"📊 Returning {len(sample_races)} races")
            return sample_races
        
    except Exception as e:
        logger.error(f"❌ Error fetching races: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch races: {str(e)}")

@app.get("/race/{race_id}/results")
async def get_race_results(race_id: str):
    """Get race classification ordered by position"""
    try:
        # Sample race results
        sample_results = [
            {
                "position": 1,
                "driver_name": "Max Verstappen",
                "constructor_name": "Red Bull Racing Honda RBPT",
                "points": 25,
                "time": "1:31:44.742",
                "fastest_lap": True,
                "fastest_lap_time": "1:33.660",
                "status": "Finished"
            },
            {
                "position": 2,
                "driver_name": "Sergio Perez",
                "constructor_name": "Red Bull Racing Honda RBPT",
                "points": 18,
                "time": "+22.457",
                "fastest_lap": False,
                "fastest_lap_time": None,
                "status": "Finished"
            },
            {
                "position": 3,
                "driver_name": "Carlos Sainz",
                "constructor_name": "Ferrari",
                "points": 15,
                "time": "+25.110",
                "fastest_lap": False,
                "fastest_lap_time": None,
                "status": "Finished"
            }
        ]
        
        logger.info(f"📊 Returning race results for {race_id}")
        return sample_results
        
    except Exception as e:
        logger.error(f"❌ Error fetching race results: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch race results: {str(e)}")

@app.get("/race/{race_id}/laps")
async def get_race_laps(race_id: str, driver: Optional[str] = None):
    """Get laps for the session (or for a given driver)"""
    try:
        # Sample lap data
        sample_laps = [
            {
                "lap_number": 1,
                "lap_time_ms": 93660,
                "sector1_ms": 31220,
                "sector2_ms": 31220,
                "sector3_ms": 31220,
                "tyre": "SOFT",
                "pit": False,
                "position": 1,
                "driver_name": "Max Verstappen"
            },
            {
                "lap_number": 2,
                "lap_time_ms": 93360,
                "sector1_ms": 31120,
                "sector2_ms": 31120,
                "sector3_ms": 31120,
                "tyre": "SOFT",
                "pit": False,
                "position": 1,
                "driver_name": "Max Verstappen"
            }
        ]
        
        if driver:
            filtered_laps = [lap for lap in sample_laps if lap["driver_name"].lower().startswith(driver.lower())]
            logger.info(f"📊 Returning {len(filtered_laps)} laps for driver {driver} in race {race_id}")
            return filtered_laps
        else:
            logger.info(f"📊 Returning {len(sample_laps)} laps for race {race_id}")
            return sample_laps
        
    except Exception as e:
        logger.error(f"❌ Error fetching race laps: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch race laps: {str(e)}")

# ============================================================================
# LIVE DATA ENDPOINTS (Mock)
# ============================================================================

@app.get("/live/{race_id}/state")
async def get_live_state(race_id: str):
    """Get current live state (mock data)"""
    try:
        # Mock live state data
        mock_state = {
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
                    "driver": "PER",
                    "position": 2,
                    "lap_number": 15,
                    "tyre": "SOFT",
                    "gap": "+22.457",
                    "last_lap_time": "1:34.120"
                }
            ],
            "last_updated": datetime.utcnow().isoformat()
        }
        
        logger.info(f"📊 Returning mock live state for {race_id}")
        return mock_state
        
    except Exception as e:
        logger.error(f"❌ Error fetching live state: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch live state: {str(e)}")

# ============================================================================
# LEGACY API ENDPOINTS (for backward compatibility)
# ============================================================================

@app.get("/api/drivers")
async def get_driver_standings_legacy(year: int = None, round: int = None, use_cache: bool = True):
    """Legacy driver standings endpoint for backward compatibility"""
    try:
        # Sample driver standings
        sample_standings = [
            {
                "position": 1,
                "driver_id": "verstappen",
                "driver_name": "Max Verstappen",
                "constructor": "Red Bull Racing Honda RBPT",
                "points": 437.0,
                "wins": 19,
                "nationality": "Dutch",
                "number": "1",
                "podiums": 0
            },
            {
                "position": 2,
                "driver_id": "norris",
                "driver_name": "Lando Norris",
                "constructor": "McLaren Mercedes",
                "points": 374.0,
                "wins": 0,
                "nationality": "British",
                "number": "4",
                "podiums": 0
            },
            {
                "position": 3,
                "driver_id": "leclerc",
                "driver_name": "Charles Leclerc",
                "constructor": "Ferrari",
                "points": 356.0,
                "wins": 0,
                "nationality": "Monegasque",
                "number": "16",
                "podiums": 0
            }
        ]
        
        logger.info(f"📊 Returning legacy driver standings for year {year or 'current'}")
        return sample_standings
        
    except Exception as e:
        logger.error(f"❌ Error fetching driver standings: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch driver standings: {str(e)}")

@app.get("/api/constructors")
async def get_constructor_standings_legacy(year: int = None, round: int = None, use_cache: bool = True):
    """Legacy constructor standings endpoint for backward compatibility"""
    try:
        # Sample constructor standings
        sample_standings = [
            {
                "position": 1,
                "constructor_id": "red_bull_racing",
                "constructor_name": "Red Bull Racing Honda RBPT",
                "points": 589.0,
                "wins": 19,
                "nationality": "Austrian"
            },
            {
                "position": 2,
                "constructor_id": "mclaren",
                "constructor_name": "McLaren Mercedes",
                "points": 666.0,
                "wins": 0,
                "nationality": "British"
            },
            {
                "position": 3,
                "constructor_id": "ferrari",
                "constructor_name": "Ferrari",
                "points": 646.0,
                "wins": 0,
                "nationality": "Italian"
            }
        ]
        
        logger.info(f"📊 Returning legacy constructor standings for year {year or 'current'}")
        return sample_standings
        
    except Exception as e:
        logger.error(f"❌ Error fetching constructor standings: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch constructor standings: {str(e)}")

@app.get("/api/races")
async def get_race_schedule_legacy(year: int = None, use_cache: bool = True):
    """Legacy race schedule endpoint for backward compatibility"""
    try:
        # Sample race schedule
        sample_schedule = [
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
        
        logger.info(f"📊 Returning legacy race schedule for year {year or 'current'}")
        return sample_schedule
        
    except Exception as e:
        logger.error(f"❌ Error fetching race schedule: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch race schedule: {str(e)}")

if __name__ == "__main__":
    uvicorn.run(
        "simple_main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
