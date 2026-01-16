"""
FastF1 Service - Handles all FastF1 API interactions
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Union
import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor
import json
import traceback

try:
    import fastf1
    from fastf1 import get_session, get_event_schedule
    from fastf1.core import Session
    FASTF1_AVAILABLE = True
except ImportError:
    FASTF1_AVAILABLE = False
    logging.warning("FastF1 not available. Install with: pip install fastf1")

from models.f1_models import (
    DriverStanding, ConstructorStanding, RaceEvent, 
    SessionData, LapData, TelemetryData, WeatherData
)

logger = logging.getLogger(__name__)

def df_to_records(df: pd.DataFrame):
    """Convert DataFrame to JSON-serializable records; convert non-serializable types."""
    if df is None or df.empty:
        return []
    
    # Convert datetimes and numpy types if present
    df2 = df.copy()
    for col in df2.columns:
        if pd.api.types.is_datetime64_any_dtype(df2[col]):
            df2[col] = df2[col].astype(str)
        # Convert numpy types to Python types
        elif pd.api.types.is_numeric_dtype(df2[col]):
            df2[col] = df2[col].astype(str)
    return df2.to_dict(orient="records")

class FastF1Service:
    """Service for interacting with FastF1 API"""
    
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.cache_dir = "./cache"
        
        if FASTF1_AVAILABLE:
            # Enable caching for better performance
            fastf1.Cache.enable_cache(self.cache_dir)
            logger.info("✅ FastF1 cache enabled")
        else:
            logger.warning("⚠️ FastF1 not available - using mock data")
    
    async def get_driver_standings(self, year: int, round: Optional[int] = None) -> List[DriverStanding]:
        """Get driver standings for a specific year and round"""
        if not FASTF1_AVAILABLE:
            return self._get_mock_driver_standings(year)
        
        try:
            # Run FastF1 in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            standings = await loop.run_in_executor(
                self.executor, 
                self._fetch_driver_standings_sync, 
                year, 
                round
            )
            return standings
        except Exception as e:
            logger.error(f"Error fetching driver standings: {e}")
            return self._get_mock_driver_standings(year)
    
    def _fetch_driver_standings_sync(self, year: int, round: Optional[int] = None) -> List[DriverStanding]:
        """Synchronous driver standings fetch"""
        try:
            # Get the session to access standings
            if round:
                session = get_session(year, round, 'R')  # Race session
            else:
                # Get the latest race session
                schedule = get_event_schedule(year)
                if schedule.empty:
                    return self._get_mock_driver_standings(year)
                
                latest_round = schedule['RoundNumber'].max()
                session = get_session(year, latest_round, 'R')
            
            session.load()
            
            if hasattr(session, 'results') and not session.results.empty:
                results = session.results
                standings = []
                
                for idx, row in results.iterrows():
                    standing = DriverStanding(
                        position=int(row.get('Position', idx + 1)),
                        driver_id=str(row.get('Abbreviation', f'driver_{idx}')),
                        driver_name=f"{row.get('FirstName', 'Unknown')} {row.get('LastName', 'Driver')}",
                        constructor=row.get('TeamName', 'Unknown Team'),
                        points=float(row.get('Points', 0)),
                        wins=int(row.get('Wins', 0)),
                        nationality=row.get('CountryCode', 'Unknown')
                    )
                    standings.append(standing)
                
                return standings
            else:
                return self._get_mock_driver_standings(year)
                
        except Exception as e:
            logger.error(f"Error in sync driver standings fetch: {e}")
            return self._get_mock_driver_standings(year)
    
    async def get_constructor_standings(self, year: int, round: Optional[int] = None) -> List[ConstructorStanding]:
        """Get constructor standings for a specific year and round"""
        if not FASTF1_AVAILABLE:
            return self._get_mock_constructor_standings(year)
        
        try:
            loop = asyncio.get_event_loop()
            standings = await loop.run_in_executor(
                self.executor,
                self._fetch_constructor_standings_sync,
                year,
                round
            )
            return standings
        except Exception as e:
            logger.error(f"Error fetching constructor standings: {e}")
            return self._get_mock_constructor_standings(year)
    
    def _fetch_constructor_standings_sync(self, year: int, round: Optional[int] = None) -> List[ConstructorStanding]:
        """Synchronous constructor standings fetch"""
        try:
            if round:
                session = get_session(year, round, 'R')
            else:
                schedule = get_event_schedule(year)
                if schedule.empty:
                    return self._get_mock_constructor_standings(year)
                
                latest_round = schedule['RoundNumber'].max()
                session = get_session(year, latest_round, 'R')
            
            session.load()
            
            if hasattr(session, 'results') and not session.results.empty:
                # Group by constructor and sum points
                constructor_points = session.results.groupby('TeamName')['Points'].sum().sort_values(ascending=False)
                
                standings = []
                for position, (constructor, points) in enumerate(constructor_points.items(), 1):
                    standing = ConstructorStanding(
                        position=position,
                        constructor_id=constructor.lower().replace(' ', '_'),
                        constructor_name=constructor,
                        points=float(points),
                        wins=0,  # Would need to calculate from race results
                        nationality='Unknown'  # Would need constructor info
                    )
                    standings.append(standing)
                
                return standings
            else:
                return self._get_mock_constructor_standings(year)
                
        except Exception as e:
            logger.error(f"Error in sync constructor standings fetch: {e}")
            return self._get_mock_constructor_standings(year)
    
    async def get_race_schedule(self, year: int) -> List[RaceEvent]:
        """Get race schedule for a specific year"""
        if not FASTF1_AVAILABLE:
            return self._get_mock_race_schedule(year)
        
        try:
            loop = asyncio.get_event_loop()
            schedule = await loop.run_in_executor(
                self.executor,
                self._fetch_race_schedule_sync,
                year
            )
            return schedule
        except Exception as e:
            logger.error(f"Error fetching race schedule: {e}")
            return self._get_mock_race_schedule(year)
    
    def _fetch_race_schedule_sync(self, year: int) -> List[RaceEvent]:
        """Synchronous race schedule fetch"""
        try:
            schedule = get_event_schedule(year)
            
            if schedule.empty:
                return self._get_mock_race_schedule(year)
            
            events = []
            for _, row in schedule.iterrows():
                event = RaceEvent(
                    round=int(row.get('RoundNumber', 0)),
                    race_name=row.get('EventName', 'Unknown Race'),
                    circuit_name=row.get('Location', 'Unknown Circuit'),
                    country=row.get('Country', 'Unknown'),
                    location=row.get('Location', 'Unknown'),
                    date=row.get('EventDate', datetime.now().date()).strftime('%Y-%m-%d'),
                    time='14:00:00Z',  # Default time
                    url=f"https://www.formula1.com/en/racing/{year}/{row.get('Location', 'unknown')}.html"
                )
                events.append(event)
            
            return events
            
        except Exception as e:
            logger.error(f"Error in sync race schedule fetch: {e}")
            return self._get_mock_race_schedule(year)
    
    async def get_driver_details(self, driver_id: str, year: int) -> Dict[str, Any]:
        """Get detailed information about a specific driver"""
        # This would require more complex FastF1 queries
        # For now, return basic info
        return {
            "driver_id": driver_id,
            "year": year,
            "details": "Driver details would be fetched from FastF1",
            "status": "not_implemented"
        }
    
    async def get_race_details(self, race_id: str, year: int) -> Dict[str, Any]:
        """Get detailed information about a specific race"""
        return {
            "race_id": race_id,
            "year": year,
            "details": "Race details would be fetched from FastF1",
            "status": "not_implemented"
        }
    
    async def get_session_data(self, session_id: str, year: int, include_telemetry: bool = False) -> Dict[str, Any]:
        """Get session data (practice, qualifying, race)"""
        if not FASTF1_AVAILABLE:
            return {"error": "FastF1 not available"}
        
        try:
            # Parse session_id (format: "round_session_type", e.g., "1_R" for round 1 race)
            parts = session_id.split('_')
            if len(parts) != 2:
                raise ValueError("Invalid session_id format")
            
            round_num = int(parts[0])
            session_type = parts[1]
            
            loop = asyncio.get_event_loop()
            session_data = await loop.run_in_executor(
                self.executor,
                self._fetch_session_data_sync,
                year,
                round_num,
                session_type,
                include_telemetry
            )
            return session_data
            
        except Exception as e:
            logger.error(f"Error fetching session data: {e}")
            return {"error": str(e)}
    
    def _fetch_session_data_sync(self, year: int, round_num: int, session_type: str, include_telemetry: bool) -> Dict[str, Any]:
        """Synchronous session data fetch"""
        try:
            session = get_session(year, round_num, session_type)
            session.load()
            
            data = {
                "year": year,
                "round": round_num,
                "session_type": session_type,
                "session_name": session.name,
                "date": session.date.strftime('%Y-%m-%d'),
                "time": session.date.strftime('%H:%M:%S'),
                "status": "completed" if session.date < datetime.now() else "upcoming"
            }
            
            if hasattr(session, 'results') and not session.results.empty:
                data["results"] = session.results.to_dict('records')
            
            if include_telemetry and hasattr(session, 'laps') and not session.laps.empty:
                # Sample telemetry data (would be much larger in reality)
                data["telemetry_sample"] = session.laps.head(10).to_dict('records')
            
            return data
            
        except Exception as e:
            logger.error(f"Error in sync session data fetch: {e}")
            return {"error": str(e)}
    
    async def get_live_session_data(self) -> Dict[str, Any]:
        """Get current live session data"""
        # This would require real-time data sources
        # For now, return mock data
        return {
            "status": "no_live_session",
            "message": "No live session currently active",
            "timestamp": datetime.utcnow().isoformat()
        }
    
    async def get_live_positions(self) -> List[Dict[str, Any]]:
        """Get current live driver positions"""
        # This would require real-time data sources
        return []
    
    async def get_driver_telemetry(self, session_id: str, driver_id: str, year: int, lap: Optional[int] = None) -> Dict[str, Any]:
        """Get telemetry data for a specific driver and session"""
        if not FASTF1_AVAILABLE:
            return {"error": "FastF1 not available"}
        
        try:
            parts = session_id.split('_')
            round_num = int(parts[0])
            session_type = parts[1]
            
            loop = asyncio.get_event_loop()
            telemetry = await loop.run_in_executor(
                self.executor,
                self._fetch_telemetry_sync,
                year,
                round_num,
                session_type,
                driver_id,
                lap
            )
            return telemetry
            
        except Exception as e:
            logger.error(f"Error fetching telemetry: {e}")
            return {"error": str(e)}
    
    def _fetch_telemetry_sync(self, year: int, round_num: int, session_type: str, driver_id: str, lap: Optional[int]) -> Dict[str, Any]:
        """Synchronous telemetry fetch"""
        try:
            session = get_session(year, round_num, session_type)
            session.load()
            
            if hasattr(session, 'laps') and not session.laps.empty:
                driver_laps = session.laps[session.laps['Driver'] == driver_id]
                
                if lap:
                    driver_laps = driver_laps[driver_laps['LapNumber'] == lap]
                
                if not driver_laps.empty:
                    # Get telemetry for the first lap
                    telemetry = driver_laps.iloc[0].get_car_data()
                    
                    return {
                        "driver_id": driver_id,
                        "year": year,
                        "round": round_num,
                        "session_type": session_type,
                        "lap": lap or driver_laps.iloc[0]['LapNumber'],
                        "telemetry": telemetry.to_dict('records') if hasattr(telemetry, 'to_dict') else []
                    }
            
            return {"error": "No telemetry data available"}
            
        except Exception as e:
            logger.error(f"Error in sync telemetry fetch: {e}")
            return {"error": str(e)}
    
    async def get_session_weather(self, session_id: str, year: int) -> Dict[str, Any]:
        """Get weather data for a specific session"""
        if not FASTF1_AVAILABLE:
            return {"error": "FastF1 not available"}
        
        try:
            parts = session_id.split('_')
            round_num = int(parts[0])
            session_type = parts[1]
            
            loop = asyncio.get_event_loop()
            weather = await loop.run_in_executor(
                self.executor,
                self._fetch_weather_sync,
                year,
                round_num,
                session_type
            )
            return weather
            
        except Exception as e:
            logger.error(f"Error fetching weather: {e}")
            return {"error": str(e)}
    
    def _fetch_weather_sync(self, year: int, round_num: int, session_type: str) -> Dict[str, Any]:
        """Synchronous weather fetch"""
        try:
            session = get_session(year, round_num, session_type)
            session.load()
            
            if hasattr(session, 'weather_data') and not session.weather_data.empty:
                return {
                    "year": year,
                    "round": round_num,
                    "session_type": session_type,
                    "weather": session.weather_data.to_dict('records')
                }
            
            return {"error": "No weather data available"}
            
        except Exception as e:
            logger.error(f"Error in sync weather fetch: {e}")
            return {"error": str(e)}
    
    async def refresh_data(self, data_type: str):
        """Background refresh of specific data type"""
        logger.info(f"🔄 Refreshing {data_type} data...")
        # Implementation would depend on data_type
        pass
    
    # New endpoints following the FastF1 API pattern from the example
    async def get_race_results(self, year: int, gp: str) -> Dict[str, Any]:
        """Get race results for a specific year and Grand Prix.
        Example: /race/2024/Bahrain/results
        """
        if not FASTF1_AVAILABLE:
            return {"error": "FastF1 not available"}
        
        try:
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                self.executor,
                self._fetch_race_results_sync,
                year,
                gp
            )
            return results
        except Exception as e:
            logger.error(f"Error fetching race results: {e}")
            traceback.print_exc()
            return {"error": str(e)}
    
    def _fetch_race_results_sync(self, year: int, gp: str) -> Dict[str, Any]:
        """Synchronous race results fetch following the example pattern"""
        try:
            # FastF1 expects the GP name as used by the library (e.g., 'Bahrain', 'Monaco')
            session = get_session(year, gp, 'R')  # Race session
            session.load()  # loads results, laps, telemetry, etc.
            
            if not hasattr(session, 'results') or session.results is None:
                return {"error": "Results not found for this session"}
            
            # session.results is a pandas DataFrame
            records = df_to_records(session.results)
            return {
                "year": year,
                "gp": gp,
                "session": 'R',
                "results": records
            }
        except Exception as e:
            traceback.print_exc()
            return {"error": str(e)}
    
    async def get_session_laps(self, year: int, gp: str, session_type: str, driver: Optional[str] = None) -> Dict[str, Any]:
        """Get laps for a session. session can be 'P1','P2','Q','R' etc.
        Optional query param driver (driver code e.g. 'VER') to filter by driver.
        Example: /race/2024/Bahrain/R/laps?driver=VER
        """
        if not FASTF1_AVAILABLE:
            return {"error": "FastF1 not available"}
        
        try:
            loop = asyncio.get_event_loop()
            laps = await loop.run_in_executor(
                self.executor,
                self._fetch_session_laps_sync,
                year,
                gp,
                session_type,
                driver
            )
            return laps
        except Exception as e:
            logger.error(f"Error fetching session laps: {e}")
            traceback.print_exc()
            return {"error": str(e)}
    
    def _fetch_session_laps_sync(self, year: int, gp: str, session_type: str, driver: Optional[str]) -> Dict[str, Any]:
        """Synchronous session laps fetch following the example pattern"""
        try:
            s = get_session(year, gp, session_type)
            s.load()
            laps = s.laps
            
            if driver:
                laps = laps.pick_driver(driver)
            
            if laps is None or laps.empty:
                return {"error": "No laps found"}
            
            # Select relevant columns and convert to records
            lap_columns = ['Driver', 'LapNumber', 'LapTime', 'Sector1', 'Sector2', 'Sector3', 'PitIn', 'PitOut']
            available_columns = [col for col in lap_columns if col in laps.columns]
            laps_data = laps[available_columns].reset_index(drop=True)
            
            records = df_to_records(laps_data)
            return {
                "year": year,
                "gp": gp,
                "session": session_type,
                "driver": driver,
                "laps": records
            }
        except Exception as e:
            traceback.print_exc()
            return {"error": str(e)}
    
    # Mock data methods for when FastF1 is not available
    def _get_mock_driver_standings(self, year: int) -> List[DriverStanding]:
        """Mock driver standings data"""
        mock_data = [
            DriverStanding(position=1, driver_id="verstappen", driver_name="Max Verstappen", 
                          constructor="Red Bull Racing", points=575.0, wins=19, nationality="Dutch"),
            DriverStanding(position=2, driver_id="leclerc", driver_name="Charles Leclerc", 
                          constructor="Ferrari", points=308.0, wins=3, nationality="Monegasque"),
            DriverStanding(position=3, driver_id="hamilton", driver_name="Lewis Hamilton", 
                          constructor="Mercedes", points=234.0, wins=0, nationality="British"),
            DriverStanding(position=4, driver_id="norris", driver_name="Lando Norris", 
                          constructor="McLaren", points=169.0, wins=0, nationality="British"),
            DriverStanding(position=5, driver_id="perez", driver_name="Sergio Perez", 
                          constructor="Red Bull Racing", points=156.0, wins=0, nationality="Mexican"),
        ]
        
        # Scale points based on year
        if year < 2024:
            for standing in mock_data:
                standing.points = standing.points * (year / 2024)
                standing.wins = int(standing.wins * (year / 2024))
        
        return mock_data
    
    def _get_mock_constructor_standings(self, year: int) -> List[ConstructorStanding]:
        """Mock constructor standings data"""
        mock_data = [
            ConstructorStanding(position=1, constructor_id="redbull", constructor_name="Red Bull Racing", 
                               points=731.0, wins=19, nationality="Austrian"),
            ConstructorStanding(position=2, constructor_id="ferrari", constructor_name="Ferrari", 
                               points=508.0, wins=4, nationality="Italian"),
            ConstructorStanding(position=3, constructor_id="mercedes", constructor_name="Mercedes", 
                               points=409.0, wins=0, nationality="German"),
            ConstructorStanding(position=4, constructor_id="mclaren", constructor_name="McLaren", 
                               points=266.0, wins=0, nationality="British"),
            ConstructorStanding(position=5, constructor_id="astonmartin", constructor_name="Aston Martin", 
                               points=206.0, wins=0, nationality="British"),
        ]
        
        # Scale points based on year
        if year < 2024:
            for standing in mock_data:
                standing.points = standing.points * (year / 2024)
                standing.wins = int(standing.wins * (year / 2024))
        
        return mock_data
    
    def _get_mock_race_schedule(self, year: int) -> List[RaceEvent]:
        """Mock race schedule data"""
        mock_races = [
            RaceEvent(round=1, race_name="Bahrain Grand Prix", circuit_name="Bahrain International Circuit", 
                     country="Bahrain", location="Sakhir", date=f"{year}-03-02", time="15:00:00Z"),
            RaceEvent(round=2, race_name="Saudi Arabian Grand Prix", circuit_name="Jeddah Corniche Circuit", 
                     country="Saudi Arabia", location="Jeddah", date=f"{year}-03-09", time="20:00:00Z"),
            RaceEvent(round=3, race_name="Australian Grand Prix", circuit_name="Albert Park Circuit", 
                     country="Australia", location="Melbourne", date=f"{year}-03-24", time="05:00:00Z"),
            RaceEvent(round=4, race_name="Japanese Grand Prix", circuit_name="Suzuka International Racing Course", 
                     country="Japan", location="Suzuka", date=f"{year}-04-07", time="06:00:00Z"),
            RaceEvent(round=5, race_name="Chinese Grand Prix", circuit_name="Shanghai International Circuit", 
                     country="China", location="Shanghai", date=f"{year}-04-21", time="08:00:00Z"),
        ]
        
        return mock_races
