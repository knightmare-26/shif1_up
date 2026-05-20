"""
Pydantic models for F1 data structures
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union
from datetime import datetime, date
from enum import Enum

class SessionType(str, Enum):
    """F1 session types"""
    FP1 = "FP1"
    FP2 = "FP2"
    FP3 = "FP3"
    Q = "Q"
    R = "R"
    SPRINT = "SPRINT"
    SPRINT_SHOOTOUT = "SPRINT_SHOOTOUT"

class DriverStanding(BaseModel):
    """Driver championship standing"""
    position: int = Field(..., description="Championship position")
    driver_id: str = Field(..., description="Unique driver identifier")
    driver_name: str = Field(..., description="Full driver name")
    constructor: str = Field(..., description="Constructor/team name")
    points: float = Field(..., description="Championship points")
    wins: int = Field(default=0, description="Number of wins")
    podiums: int = Field(default=0, description="Number of podiums")
    nationality: str = Field(..., description="Driver nationality")
    number: Optional[int] = Field(None, description="Driver number")

class ConstructorStanding(BaseModel):
    """Constructor championship standing"""
    position: int = Field(..., description="Championship position")
    constructor_id: str = Field(..., description="Unique constructor identifier")
    constructor_name: str = Field(..., description="Constructor name")
    points: float = Field(..., description="Championship points")
    wins: int = Field(default=0, description="Number of wins")
    nationality: str = Field(..., description="Constructor nationality")

class RaceEvent(BaseModel):
    """F1 race event"""
    round: int = Field(..., description="Round number")
    race_name: str = Field(..., description="Official race name")
    circuit_name: str = Field(..., description="Circuit name")
    country: str = Field(..., description="Country")
    location: str = Field(..., description="Location/city")
    date: str = Field(..., description="Race date (YYYY-MM-DD)")
    time: str = Field(..., description="Race time (HH:MM:SSZ)")
    url: Optional[str] = Field(None, description="Official race URL")

class SessionData(BaseModel):
    """F1 session data"""
    year: int = Field(..., description="Season year")
    round: int = Field(..., description="Round number")
    session_type: SessionType = Field(..., description="Type of session")
    session_name: str = Field(..., description="Session name")
    date: str = Field(..., description="Session date")
    time: str = Field(..., description="Session time")
    status: str = Field(..., description="Session status")
    results: Optional[List[Dict[str, Any]]] = Field(None, description="Session results")

class LapData(BaseModel):
    """Lap data for a driver"""
    driver_id: str = Field(..., description="Driver identifier")
    lap_number: int = Field(..., description="Lap number")
    lap_time: Optional[float] = Field(None, description="Lap time in seconds")
    sector1_time: Optional[float] = Field(None, description="Sector 1 time")
    sector2_time: Optional[float] = Field(None, description="Sector 2 time")
    sector3_time: Optional[float] = Field(None, description="Sector 3 time")
    position: int = Field(..., description="Position at end of lap")
    compound: Optional[str] = Field(None, description="Tire compound")
    tyre_life: Optional[int] = Field(None, description="Tire life in laps")

class TelemetryData(BaseModel):
    """Telemetry data point"""
    timestamp: str = Field(..., description="Timestamp")
    driver_id: str = Field(..., description="Driver identifier")
    lap_number: int = Field(..., description="Lap number")
    distance: float = Field(..., description="Distance along track")
    speed: float = Field(..., description="Speed in km/h")
    rpm: int = Field(..., description="Engine RPM")
    throttle: float = Field(..., description="Throttle position (0-100)")
    brake: bool = Field(..., description="Brake applied")
    gear: int = Field(..., description="Current gear")
    drs: bool = Field(..., description="DRS active")
    x: float = Field(..., description="X coordinate")
    y: float = Field(..., description="Y coordinate")

class WeatherData(BaseModel):
    """Weather data for a session"""
    timestamp: str = Field(..., description="Timestamp")
    air_temp: float = Field(..., description="Air temperature in Celsius")
    track_temp: float = Field(..., description="Track temperature in Celsius")
    humidity: float = Field(..., description="Humidity percentage")
    pressure: float = Field(..., description="Air pressure in hPa")
    wind_speed: float = Field(..., description="Wind speed in km/h")
    wind_direction: float = Field(..., description="Wind direction in degrees")
    rain: bool = Field(..., description="Rain detected")

class LivePosition(BaseModel):
    """Live driver position"""
    driver_id: str = Field(..., description="Driver identifier")
    driver_name: str = Field(..., description="Driver name")
    position: int = Field(..., description="Current position")
    gap: Optional[str] = Field(None, description="Gap to leader")
    interval: Optional[str] = Field(None, description="Gap to car ahead")
    last_lap_time: Optional[str] = Field(None, description="Last lap time")
    best_lap_time: Optional[str] = Field(None, description="Best lap time")
    sector: int = Field(..., description="Current sector")
    status: str = Field(..., description="Driver status")

class LiveSession(BaseModel):
    """Live session information"""
    session_id: str = Field(..., description="Session identifier")
    session_name: str = Field(..., description="Session name")
    status: str = Field(..., description="Session status")
    elapsed_time: Optional[str] = Field(None, description="Elapsed session time")
    remaining_time: Optional[str] = Field(None, description="Remaining session time")
    track_status: str = Field(..., description="Track status")
    positions: List[LivePosition] = Field(default_factory=list, description="Current positions")

class CircuitInfo(BaseModel):
    """Circuit information"""
    circuit_id: str = Field(..., description="Circuit identifier")
    circuit_name: str = Field(..., description="Circuit name")
    country: str = Field(..., description="Country")
    location: str = Field(..., description="Location")
    latitude: float = Field(..., description="Latitude")
    longitude: float = Field(..., description="Longitude")
    altitude: int = Field(..., description="Altitude in meters")
    length: float = Field(..., description="Circuit length in km")
    corners: int = Field(..., description="Number of corners")
    laps: int = Field(..., description="Number of laps")
    race_distance: float = Field(..., description="Race distance in km")
    record_lap: Optional[str] = Field(None, description="Lap record")
    record_holder: Optional[str] = Field(None, description="Record holder")
    record_year: Optional[int] = Field(None, description="Record year")

class DriverInfo(BaseModel):
    """Detailed driver information"""
    driver_id: str = Field(..., description="Driver identifier")
    driver_name: str = Field(..., description="Full driver name")
    first_name: str = Field(..., description="First name")
    last_name: str = Field(..., description="Last name")
    date_of_birth: Optional[str] = Field(None, description="Date of birth")
    nationality: str = Field(..., description="Nationality")
    number: Optional[int] = Field(None, description="Driver number")
    code: Optional[str] = Field(None, description="Driver code")
    constructor: str = Field(..., description="Current constructor")
    career_stats: Optional[Dict[str, Any]] = Field(None, description="Career statistics")

class ConstructorInfo(BaseModel):
    """Detailed constructor information"""
    constructor_id: str = Field(..., description="Constructor identifier")
    constructor_name: str = Field(..., description="Constructor name")
    nationality: str = Field(..., description="Nationality")
    founded: Optional[int] = Field(None, description="Year founded")
    base: Optional[str] = Field(None, description="Base location")
    team_principal: Optional[str] = Field(None, description="Team principal")
    drivers: List[str] = Field(default_factory=list, description="Current drivers")
    career_stats: Optional[Dict[str, Any]] = Field(None, description="Career statistics")

class RaceResult(BaseModel):
    """Race result"""
    position: int = Field(..., description="Finishing position")
    driver_id: str = Field(..., description="Driver identifier")
    driver_name: str = Field(..., description="Driver name")
    constructor: str = Field(..., description="Constructor")
    grid_position: int = Field(..., description="Starting grid position")
    points: float = Field(..., description="Points scored")
    time: Optional[str] = Field(None, description="Race time")
    gap: Optional[str] = Field(None, description="Gap to winner")
    fastest_lap: bool = Field(default=False, description="Fastest lap")
    fastest_lap_time: Optional[str] = Field(None, description="Fastest lap time")
    status: str = Field(..., description="Race status")
    laps: int = Field(..., description="Laps completed")

class QualifyingResult(BaseModel):
    """Qualifying result"""
    position: int = Field(..., description="Qualifying position")
    driver_id: str = Field(..., description="Driver identifier")
    driver_name: str = Field(..., description="Driver name")
    constructor: str = Field(..., description="Constructor")
    q1_time: Optional[str] = Field(None, description="Q1 time")
    q2_time: Optional[str] = Field(None, description="Q2 time")
    q3_time: Optional[str] = Field(None, description="Q3 time")
    best_time: str = Field(..., description="Best qualifying time")

class PracticeResult(BaseModel):
    """Practice session result"""
    position: int = Field(..., description="Session position")
    driver_id: str = Field(..., description="Driver identifier")
    driver_name: str = Field(..., description="Driver name")
    constructor: str = Field(..., description="Constructor")
    best_time: str = Field(..., description="Best lap time")
    total_laps: int = Field(..., description="Total laps completed")
    gap: Optional[str] = Field(None, description="Gap to fastest")

class SeasonSummary(BaseModel):
    """Season summary"""
    year: int = Field(..., description="Season year")
    total_races: int = Field(..., description="Total races")
    completed_races: int = Field(..., description="Completed races")
    driver_champion: Optional[str] = Field(None, description="Driver champion")
    constructor_champion: Optional[str] = Field(None, description="Constructor champion")
    most_wins: Optional[str] = Field(None, description="Driver with most wins")
    most_poles: Optional[str] = Field(None, description="Driver with most pole positions")
    most_fastest_laps: Optional[str] = Field(None, description="Driver with most fastest laps")

class APIResponse(BaseModel):
    """Standard API response wrapper"""
    success: bool = Field(..., description="Request success status")
    data: Optional[Any] = Field(None, description="Response data")
    message: Optional[str] = Field(None, description="Response message")
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat(), description="Response timestamp")
    cache_hit: bool = Field(default=False, description="Whether data came from cache")

class ErrorResponse(BaseModel):
    """Error response model"""
    success: bool = Field(default=False, description="Request success status")
    error: str = Field(..., description="Error message")
    error_code: Optional[str] = Field(None, description="Error code")
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat(), description="Error timestamp")
