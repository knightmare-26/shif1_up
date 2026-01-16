#!/usr/bin/env python3
"""
F1 Prediction Worker
Subscribes to Redis channels and generates predictions based on live data
"""

import asyncio
import argparse
import logging
import os
import sys
import json
from datetime import datetime
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.services.redis_service import RedisService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class PredictionWorker:
    """F1 prediction worker service"""
    
    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self.redis_service = RedisService(redis_url)
        self.is_running = False
        
        # Prediction models (simplified)
        self.lap_time_history = {}
        self.position_history = {}
        
    async def initialize(self):
        """Initialize the prediction worker"""
        await self.redis_service.initialize()
        logger.info("✅ Prediction worker initialized")
    
    async def cleanup(self):
        """Cleanup the prediction worker"""
        self.is_running = False
        await self.redis_service.cleanup()
        logger.info("✅ Prediction worker cleanup completed")
    
    async def start_worker(self):
        """Start the prediction worker"""
        try:
            logger.info("🚀 Starting prediction worker...")
            self.is_running = True
            
            # Subscribe to all race update channels
            pubsub = self.redis_service.get_pubsub()
            await pubsub.psubscribe("race:*:updates")
            
            logger.info("📡 Subscribed to race update channels")
            
            # Process messages
            async for message in pubsub.listen():
                if not self.is_running:
                    break
                
                if message["type"] == "pmessage":
                    try:
                        data = json.loads(message["data"])
                        await self._process_race_update(data)
                    except json.JSONDecodeError:
                        continue
                    except Exception as e:
                        logger.error(f"❌ Error processing message: {str(e)}")
                        continue
            
        except Exception as e:
            logger.error(f"❌ Error in prediction worker: {str(e)}")
        finally:
            self.is_running = False
            logger.info("🏁 Prediction worker stopped")
    
    async def _process_race_update(self, data: Dict[str, Any]):
        """Process race update and generate predictions"""
        try:
            race_id = data.get("race_id")
            update_type = data.get("update", {}).get("type")
            
            if not race_id or not update_type:
                return
            
            logger.debug(f"📊 Processing {update_type} update for {race_id}")
            
            # Update historical data
            await self._update_historical_data(race_id, data)
            
            # Generate predictions based on update type
            if update_type == "lap_update":
                await self._generate_lap_predictions(race_id)
            elif update_type == "state_update":
                await self._generate_race_predictions(race_id)
            
        except Exception as e:
            logger.error(f"❌ Error processing race update: {str(e)}")
    
    async def _update_historical_data(self, race_id: str, data: Dict[str, Any]):
        """Update historical data for predictions"""
        try:
            if race_id not in self.lap_time_history:
                self.lap_time_history[race_id] = {}
                self.position_history[race_id] = {}
            
            update = data.get("update", {})
            
            if "drivers" in update:
                for driver_data in update["drivers"]:
                    driver = driver_data["driver"]
                    
                    # Store lap time data
                    if "lap_time" in driver_data and driver_data["lap_time"]:
                        if driver not in self.lap_time_history[race_id]:
                            self.lap_time_history[race_id][driver] = []
                        
                        # Convert lap time to seconds
                        lap_time_str = driver_data["lap_time"]
                        try:
                            # Parse time format (e.g., "0:01:23.456")
                            time_parts = lap_time_str.split(":")
                            if len(time_parts) == 3:
                                minutes = int(time_parts[0])
                                seconds = float(time_parts[1])
                                lap_time_seconds = minutes * 60 + seconds
                                self.lap_time_history[race_id][driver].append(lap_time_seconds)
                        except (ValueError, IndexError):
                            continue
                    
                    # Store position data
                    if "position" in driver_data:
                        if driver not in self.position_history[race_id]:
                            self.position_history[race_id][driver] = []
                        self.position_history[race_id][driver].append(driver_data["position"])
            
        except Exception as e:
            logger.error(f"❌ Error updating historical data: {str(e)}")
    
    async def _generate_lap_predictions(self, race_id: str):
        """Generate predictions based on lap data"""
        try:
            if race_id not in self.lap_time_history:
                return
            
            predictions = {
                "race_id": race_id,
                "timestamp": datetime.utcnow().isoformat(),
                "type": "lap_predictions",
                "predictions": {}
            }
            
            # Generate predictions for each driver
            for driver, lap_times in self.lap_time_history[race_id].items():
                if len(lap_times) < 3:  # Need at least 3 laps for prediction
                    continue
                
                # Simple prediction: average of last 3 laps
                recent_laps = lap_times[-3:]
                predicted_lap_time = np.mean(recent_laps)
                lap_time_std = np.std(recent_laps)
                
                predictions["predictions"][driver] = {
                    "predicted_lap_time": round(predicted_lap_time, 3),
                    "confidence": max(0, 1 - (lap_time_std / predicted_lap_time)),
                    "trend": self._calculate_trend(lap_times),
                    "based_on_laps": len(lap_times)
                }
            
            # Store prediction
            await self.redis_service.set_prediction(race_id, predictions)
            logger.debug(f"📊 Generated lap predictions for {race_id}")
            
        except Exception as e:
            logger.error(f"❌ Error generating lap predictions: {str(e)}")
    
    async def _generate_race_predictions(self, race_id: str):
        """Generate race outcome predictions"""
        try:
            if race_id not in self.position_history:
                return
            
            predictions = {
                "race_id": race_id,
                "timestamp": datetime.utcnow().isoformat(),
                "type": "race_predictions",
                "predictions": {}
            }
            
            # Get current positions
            current_positions = {}
            for driver, positions in self.position_history[race_id].items():
                if positions:
                    current_positions[driver] = positions[-1]
            
            # Generate podium predictions
            podium_predictions = self._predict_podium(current_positions, race_id)
            predictions["predictions"]["podium"] = podium_predictions
            
            # Generate finish position predictions
            position_predictions = self._predict_finish_positions(current_positions, race_id)
            predictions["predictions"]["finish_positions"] = position_predictions
            
            # Store prediction
            await self.redis_service.set_prediction(race_id, predictions)
            logger.info(f"📊 Generated race predictions for {race_id}")
            
        except Exception as e:
            logger.error(f"❌ Error generating race predictions: {str(e)}")
    
    def _calculate_trend(self, lap_times: List[float]) -> str:
        """Calculate lap time trend"""
        if len(lap_times) < 2:
            return "stable"
        
        recent = lap_times[-3:] if len(lap_times) >= 3 else lap_times
        older = lap_times[-6:-3] if len(lap_times) >= 6 else lap_times[:-3] if len(lap_times) > 3 else []
        
        if not older:
            return "stable"
        
        recent_avg = np.mean(recent)
        older_avg = np.mean(older)
        
        if recent_avg < older_avg * 0.99:  # 1% improvement
            return "improving"
        elif recent_avg > older_avg * 1.01:  # 1% degradation
            return "degrading"
        else:
            return "stable"
    
    def _predict_podium(self, current_positions: Dict[str, int], race_id: str) -> Dict[str, Any]:
        """Predict podium finishers"""
        try:
            # Sort drivers by current position
            sorted_drivers = sorted(current_positions.items(), key=lambda x: x[1])
            
            if len(sorted_drivers) < 3:
                return {"error": "Not enough drivers for podium prediction"}
            
            # Simple prediction: current top 3 with some probability
            podium = {
                "1st": {
                    "driver": sorted_drivers[0][0],
                    "probability": 0.6,
                    "current_position": sorted_drivers[0][1]
                },
                "2nd": {
                    "driver": sorted_drivers[1][0],
                    "probability": 0.5,
                    "current_position": sorted_drivers[1][1]
                },
                "3rd": {
                    "driver": sorted_drivers[2][0],
                    "probability": 0.4,
                    "current_position": sorted_drivers[2][1]
                }
            }
            
            return podium
            
        except Exception as e:
            logger.error(f"❌ Error predicting podium: {str(e)}")
            return {"error": "Failed to predict podium"}
    
    def _predict_finish_positions(self, current_positions: Dict[str, int], race_id: str) -> Dict[str, Any]:
        """Predict final finish positions"""
        try:
            # Sort drivers by current position
            sorted_drivers = sorted(current_positions.items(), key=lambda x: x[1])
            
            predictions = {}
            for i, (driver, position) in enumerate(sorted_drivers):
                # Simple prediction: current position with some uncertainty
                confidence = max(0.3, 1.0 - (i * 0.1))  # Decreasing confidence for lower positions
                
                predictions[driver] = {
                    "predicted_position": position,
                    "confidence": round(confidence, 2),
                    "current_position": position,
                    "position_change": 0  # No change prediction in this simple model
                }
            
            return predictions
            
        except Exception as e:
            logger.error(f"❌ Error predicting finish positions: {str(e)}")
            return {"error": "Failed to predict finish positions"}

async def main():
    """Main prediction worker function"""
    parser = argparse.ArgumentParser(description='F1 Prediction Worker')
    parser.add_argument('--redis-url', default='redis://localhost:6379', help='Redis URL')
    
    args = parser.parse_args()
    
    # Create worker
    worker = PredictionWorker(redis_url=args.redis_url)
    
    try:
        # Initialize and start worker
        await worker.initialize()
        await worker.start_worker()
    
    except KeyboardInterrupt:
        logger.info("🛑 Prediction worker stopped by user")
    
    except Exception as e:
        logger.error(f"❌ Prediction worker error: {str(e)}")
    
    finally:
        await worker.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
