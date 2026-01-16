"""
Ergast API Service - Handles historical F1 data from Ergast API
This provides accurate historical data for years where FastF1 session data is incomplete
"""

import asyncio
import aiohttp
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
import json

from models.f1_models import DriverStanding, ConstructorStanding, RaceEvent

logger = logging.getLogger(__name__)

class ErgastService:
    """Service for interacting with Ergast API for historical F1 data"""
    
    def __init__(self):
        self.base_url = "https://ergast.com/api/f1"
        self.session = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def get_driver_standings(self, year: int, round: Optional[int] = None) -> List[DriverStanding]:
        """Get driver standings from Ergast API"""
        try:
            if round:
                url = f"{self.base_url}/{year}/{round}/driverStandings.json"
            else:
                url = f"{self.base_url}/{year}/driverStandings.json"
            
            timeout = aiohttp.ClientTimeout(total=10)
            async with self.session.get(url, timeout=timeout) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._parse_driver_standings(data)
                else:
                    logger.error(f"Ergast API error: {response.status}")
                    return self._get_fallback_driver_standings(year)
        except Exception as e:
            logger.error(f"Error fetching driver standings from Ergast: {e}")
            return self._get_fallback_driver_standings(year)
    
    async def get_constructor_standings(self, year: int, round: Optional[int] = None) -> List[ConstructorStanding]:
        """Get constructor standings from Ergast API"""
        try:
            if round:
                url = f"{self.base_url}/{year}/{round}/constructorStandings.json"
            else:
                url = f"{self.base_url}/{year}/constructorStandings.json"
            
            timeout = aiohttp.ClientTimeout(total=10)
            async with self.session.get(url, timeout=timeout) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._parse_constructor_standings(data)
                else:
                    logger.error(f"Ergast API error: {response.status}")
                    return self._get_fallback_constructor_standings(year)
        except Exception as e:
            logger.error(f"Error fetching constructor standings from Ergast: {e}")
            return self._get_fallback_constructor_standings(year)
    
    async def get_race_schedule(self, year: int) -> List[RaceEvent]:
        """Get race schedule from Ergast API"""
        try:
            url = f"{self.base_url}/{year}.json"
            
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._parse_race_schedule(data)
                else:
                    logger.error(f"Ergast API error: {response.status}")
                    return []
        except Exception as e:
            logger.error(f"Error fetching race schedule from Ergast: {e}")
            return []
    
    def _parse_driver_standings(self, data: Dict[str, Any]) -> List[DriverStanding]:
        """Parse driver standings from Ergast API response"""
        standings = []
        
        try:
            mrd = data.get('MRData', {})
            standings_data = mrd.get('StandingsTable', {}).get('StandingsLists', [])
            
            if not standings_data:
                return standings
            
            drivers_data = standings_data[0].get('DriverStandings', [])
            
            for driver_data in drivers_data:
                driver_info = driver_data.get('Driver', {})
                constructor_info = driver_data.get('Constructors', [{}])[0]
                
                standing = DriverStanding(
                    position=int(driver_data.get('position', 0)),
                    driver_id=driver_info.get('driverId', ''),
                    driver_name=f"{driver_info.get('givenName', '')} {driver_info.get('familyName', '')}".strip(),
                    constructor=constructor_info.get('name', ''),
                    points=float(driver_data.get('points', 0)),
                    wins=int(driver_data.get('wins', 0)),
                    nationality=driver_info.get('nationality', ''),
                    number=driver_info.get('permanentNumber', ''),
                    podiums=0  # Ergast doesn't provide podiums directly
                )
                standings.append(standing)
                
        except Exception as e:
            logger.error(f"Error parsing driver standings: {e}")
        
        return standings
    
    def _parse_constructor_standings(self, data: Dict[str, Any]) -> List[ConstructorStanding]:
        """Parse constructor standings from Ergast API response"""
        standings = []
        
        try:
            mrd = data.get('MRData', {})
            standings_data = mrd.get('StandingsTable', {}).get('StandingsLists', [])
            
            if not standings_data:
                return standings
            
            constructors_data = standings_data[0].get('ConstructorStandings', [])
            
            for constructor_data in constructors_data:
                constructor_info = constructor_data.get('Constructor', {})
                
                standing = ConstructorStanding(
                    position=int(constructor_data.get('position', 0)),
                    constructor_id=constructor_info.get('constructorId', ''),
                    constructor_name=constructor_info.get('name', ''),
                    points=float(constructor_data.get('points', 0)),
                    wins=int(constructor_data.get('wins', 0)),
                    nationality=constructor_info.get('nationality', '')
                )
                standings.append(standing)
                
        except Exception as e:
            logger.error(f"Error parsing constructor standings: {e}")
        
        return standings
    
    def _parse_race_schedule(self, data: Dict[str, Any]) -> List[RaceEvent]:
        """Parse race schedule from Ergast API response"""
        events = []
        
        try:
            mrd = data.get('MRData', {})
            races_data = mrd.get('RaceTable', {}).get('Races', [])
            
            for race_data in races_data:
                circuit = race_data.get('Circuit', {})
                location = circuit.get('Location', {})
                
                event = RaceEvent(
                    round_number=int(race_data.get('round', 0)),
                    race_name=race_data.get('raceName', ''),
                    circuit_name=circuit.get('circuitName', ''),
                    country=circuit.get('Location', {}).get('country', ''),
                    location=circuit.get('Location', {}).get('locality', ''),
                    date=race_data.get('date', ''),
                    time=race_data.get('time', ''),
                    url=race_data.get('url', '')
                )
                events.append(event)
                
        except Exception as e:
            logger.error(f"Error parsing race schedule: {e}")
        
        return events
    
    def _get_fallback_driver_standings(self, year: int) -> List[DriverStanding]:
        """Fallback driver standings when API fails"""
        # Return the correct 2024 data you provided
        if year == 2024:
            return [
                DriverStanding(position=1, driver_id="verstappen", driver_name="Max Verstappen", 
                             constructor="Red Bull Racing Honda RBPT", points=437.0, wins=19, 
                             nationality="Dutch", number="1", podiums=0),
                DriverStanding(position=2, driver_id="norris", driver_name="Lando Norris", 
                             constructor="McLaren Mercedes", points=374.0, wins=0, 
                             nationality="British", number="4", podiums=0),
                DriverStanding(position=3, driver_id="leclerc", driver_name="Charles Leclerc", 
                             constructor="Ferrari", points=356.0, wins=0, 
                             nationality="Monegasque", number="16", podiums=0),
                DriverStanding(position=4, driver_id="piastri", driver_name="Oscar Piastri", 
                             constructor="McLaren Mercedes", points=292.0, wins=0, 
                             nationality="Australian", number="81", podiums=0),
                DriverStanding(position=5, driver_id="sainz", driver_name="Carlos Sainz", 
                             constructor="Ferrari", points=290.0, wins=0, 
                             nationality="Spanish", number="55", podiums=0),
                DriverStanding(position=6, driver_id="russell", driver_name="George Russell", 
                             constructor="Mercedes", points=245.0, wins=0, 
                             nationality="British", number="63", podiums=0),
                DriverStanding(position=7, driver_id="hamilton", driver_name="Lewis Hamilton", 
                             constructor="Mercedes", points=223.0, wins=0, 
                             nationality="British", number="44", podiums=0),
                DriverStanding(position=8, driver_id="perez", driver_name="Sergio Perez", 
                             constructor="Red Bull Racing Honda RBPT", points=152.0, wins=0, 
                             nationality="Mexican", number="11", podiums=0),
                DriverStanding(position=9, driver_id="alonso", driver_name="Fernando Alonso", 
                             constructor="Aston Martin Aramco Mercedes", points=70.0, wins=0, 
                             nationality="Spanish", number="14", podiums=0),
                DriverStanding(position=10, driver_id="gasly", driver_name="Pierre Gasly", 
                             constructor="Alpine Renault", points=42.0, wins=0, 
                             nationality="French", number="10", podiums=0),
            ]
        return []
    
    def _get_fallback_constructor_standings(self, year: int) -> List[ConstructorStanding]:
        """Fallback constructor standings when API fails"""
        if year == 2024:
            return [
                ConstructorStanding(position=1, constructor_id="red_bull_racing", 
                                  constructor_name="Red Bull Racing Honda RBPT", points=589.0, 
                                  wins=19, nationality="Austrian"),
                ConstructorStanding(position=2, constructor_id="mclaren", 
                                  constructor_name="McLaren Mercedes", points=666.0, 
                                  wins=0, nationality="British"),
                ConstructorStanding(position=3, constructor_id="ferrari", 
                                  constructor_name="Ferrari", points=646.0, 
                                  wins=0, nationality="Italian"),
                ConstructorStanding(position=4, constructor_id="mercedes", 
                                  constructor_name="Mercedes", points=468.0, 
                                  wins=0, nationality="German"),
                ConstructorStanding(position=5, constructor_id="aston_martin", 
                                  constructor_name="Aston Martin Aramco Mercedes", points=94.0, 
                                  wins=0, nationality="British"),
            ]
        return []
