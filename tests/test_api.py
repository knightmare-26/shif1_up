"""
Unit tests for F1 API endpoints
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient
import sys
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.main import app
from api.services.duckdb_service import DuckDBService
from api.services.redis_service import RedisService

class TestAPI:
    """Test class for API endpoints"""
    
    @pytest.fixture
    def client(self):
        """Create test client"""
        return TestClient(app)
    
    @pytest.fixture
    def mock_duckdb_service(self):
        """Mock DuckDB service"""
        mock = Mock(spec=DuckDBService)
        mock.initialize = AsyncMock()
        mock.cleanup = AsyncMock()
        return mock
    
    @pytest.fixture
    def mock_redis_service(self):
        """Mock Redis service"""
        mock = Mock(spec=RedisService)
        mock.initialize = AsyncMock()
        mock.cleanup = AsyncMock()
        return mock
    
    def test_health_endpoint(self, client):
        """Test health check endpoint"""
        response = client.get("/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "ok"
        assert "timestamp" in data
        assert "service" in data
    
    @patch('api.main.duckdb_service')
    def test_get_drivers_no_year(self, mock_duckdb, client):
        """Test get drivers endpoint without year parameter"""
        # Mock DuckDB service
        mock_duckdb.get_drivers_by_year.return_value = []
        mock_duckdb.get_all_drivers.return_value = [
            {
                "driver_id": "verstappen",
                "full_name": "Max Verstappen",
                "nationality": "Dutch",
                "number": 1
            }
        ]
        
        response = client.get("/drivers")
        assert response.status_code == 200
        
        data = response.json()
        assert len(data) == 1
        assert data[0]["driver_id"] == "verstappen"
        assert data[0]["full_name"] == "Max Verstappen"
    
    @patch('api.main.duckdb_service')
    def test_get_drivers_with_year(self, mock_duckdb, client):
        """Test get drivers endpoint with year parameter"""
        # Mock DuckDB service
        mock_duckdb.get_drivers_by_year.return_value = [
            {
                "driver_id": "verstappen",
                "full_name": "Max Verstappen",
                "nationality": "Dutch",
                "number": 1
            }
        ]
        
        response = client.get("/drivers?year=2024")
        assert response.status_code == 200
        
        data = response.json()
        assert len(data) == 1
        assert data[0]["driver_id"] == "verstappen"
    
    @patch('api.main.duckdb_service')
    def test_get_races_with_year(self, mock_duckdb, client):
        """Test get races endpoint with year parameter"""
        # Mock DuckDB service
        mock_duckdb.get_races_by_year.return_value = [
            {
                "race_id": "2024_Bahrain",
                "year": 2024,
                "round": 1,
                "gp": "Bahrain",
                "date": "2024-03-02",
                "circuit_name": "Bahrain International Circuit",
                "country": "Bahrain"
            }
        ]
        
        response = client.get("/races?year=2024")
        assert response.status_code == 200
        
        data = response.json()
        assert len(data) == 1
        assert data[0]["race_id"] == "2024_Bahrain"
        assert data[0]["year"] == 2024
    
    @patch('api.main.duckdb_service')
    def test_get_race_results(self, mock_duckdb, client):
        """Test get race results endpoint"""
        # Mock DuckDB service
        mock_duckdb.get_race_results.return_value = [
            {
                "position": 1,
                "driver_name": "Max Verstappen",
                "constructor_name": "Red Bull Racing",
                "points": 25,
                "time": "1:31:44.742",
                "fastest_lap": True,
                "fastest_lap_time": "1:33.660",
                "status": "Finished"
            }
        ]
        
        response = client.get("/race/2024_Bahrain/results")
        assert response.status_code == 200
        
        data = response.json()
        assert len(data) == 1
        assert data[0]["position"] == 1
        assert data[0]["driver_name"] == "Max Verstappen"
    
    @patch('api.main.duckdb_service')
    def test_get_race_laps(self, mock_duckdb, client):
        """Test get race laps endpoint"""
        # Mock DuckDB service
        mock_duckdb.get_race_laps.return_value = [
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
            }
        ]
        
        response = client.get("/race/2024_Bahrain/laps")
        assert response.status_code == 200
        
        data = response.json()
        assert len(data) == 1
        assert data[0]["lap_number"] == 1
        assert data[0]["driver_name"] == "Max Verstappen"
    
    @patch('api.main.duckdb_service')
    def test_get_race_laps_with_driver(self, mock_duckdb, client):
        """Test get race laps endpoint with driver filter"""
        # Mock DuckDB service
        mock_duckdb.get_race_laps.return_value = [
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
            }
        ]
        
        response = client.get("/race/2024_Bahrain/laps?driver=VER")
        assert response.status_code == 200
        
        data = response.json()
        assert len(data) == 1
        assert data[0]["driver_name"] == "Max Verstappen"
    
    @patch('api.main.redis_service')
    def test_get_live_state(self, mock_redis, client):
        """Test get live state endpoint"""
        # Mock Redis service
        mock_redis.get_live_state.return_value = {
            "race_id": "2024_Bahrain",
            "timestamp": "2024-03-02T15:30:00Z",
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
                }
            ]
        }
        
        response = client.get("/live/2024_Bahrain/state")
        assert response.status_code == 200
        
        data = response.json()
        assert data["race_id"] == "2024_Bahrain"
        assert data["session_status"] == "live"
        assert data["current_lap"] == 15
    
    @patch('api.main.redis_service')
    def test_get_live_state_not_found(self, mock_redis, client):
        """Test get live state endpoint when no data available"""
        # Mock Redis service
        mock_redis.get_live_state.return_value = None
        
        response = client.get("/live/2024_Bahrain/state")
        assert response.status_code == 200
        
        data = response.json()
        assert "error" in data
        assert "No live data available" in data["error"]
    
    def test_legacy_driver_standings_endpoint(self, client):
        """Test legacy driver standings endpoint for backward compatibility"""
        response = client.get("/api/drivers")
        # This should work even if it returns empty data
        assert response.status_code == 200

if __name__ == "__main__":
    pytest.main([__file__])
