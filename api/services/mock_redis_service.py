"""
Mock Redis Service for Development
Provides Redis-like functionality without requiring Redis installation
"""

import json
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, AsyncGenerator
import logging

logger = logging.getLogger(__name__)

class MockRedisService:
    """Mock Redis service for development without Redis installation"""
    
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self.data = {}
        self.pubsub_channels = {}
        self.subscribers = {}
        
    async def initialize(self):
        """Initialize the mock Redis service"""
        logger.info("✅ Mock Redis service initialized")
        
    async def cleanup(self):
        """Cleanup the mock Redis service"""
        logger.info("✅ Mock Redis service cleanup completed")
    
    def get_pubsub(self):
        """Get mock pub/sub client"""
        return MockPubSub(self)
    
    async def set_live_state(self, race_id: str, state: Dict[str, Any], ttl: int = 3600) -> bool:
        """Set live state for a race"""
        try:
            key = f"race:{race_id}:state"
            state_data = {
                "race_id": race_id,
                "timestamp": datetime.utcnow().isoformat(),
                "state": state
            }
            
            self.data[key] = state_data
            logger.debug(f"✅ Set live state for race {race_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error setting live state: {str(e)}")
            return False
    
    async def get_live_state(self, race_id: str) -> Optional[Dict[str, Any]]:
        """Get live state for a race"""
        try:
            key = f"race:{race_id}:state"
            return self.data.get(key)
            
        except Exception as e:
            logger.error(f"❌ Error getting live state: {str(e)}")
            return None
    
    async def publish_update(self, race_id: str, update: Dict[str, Any]) -> bool:
        """Publish live update for a race"""
        try:
            channel = f"race:{race_id}:updates"
            update_data = {
                "race_id": race_id,
                "timestamp": datetime.utcnow().isoformat(),
                "update": update
            }
            
            # Store in pubsub channels
            if channel not in self.pubsub_channels:
                self.pubsub_channels[channel] = []
            
            self.pubsub_channels[channel].append(update_data)
            
            # Notify subscribers
            if channel in self.subscribers:
                for subscriber in self.subscribers[channel]:
                    await subscriber.put(update_data)
            
            logger.debug(f"✅ Published update for race {race_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error publishing update: {str(e)}")
            return False
    
    async def subscribe_to_race(self, race_id: str) -> AsyncGenerator[Dict[str, Any], None]:
        """Subscribe to live updates for a race"""
        try:
            channel = f"race:{race_id}:updates"
            
            # Create a queue for this subscriber
            queue = asyncio.Queue()
            if channel not in self.subscribers:
                self.subscribers[channel] = []
            self.subscribers[channel].append(queue)
            
            # Send any existing messages
            if channel in self.pubsub_channels:
                for message in self.pubsub_channels[channel][-10:]:  # Last 10 messages
                    await queue.put(message)
            
            # Listen for new messages
            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=1.0)
                    yield message
                except asyncio.TimeoutError:
                    continue
                    
        except Exception as e:
            logger.error(f"❌ Error subscribing to race {race_id}: {str(e)}")
    
    async def set_prediction(self, race_id: str, prediction: Dict[str, Any], ttl: int = 3600) -> bool:
        """Set prediction for a race"""
        try:
            key = f"race:{race_id}:predictions"
            prediction_data = {
                "race_id": race_id,
                "timestamp": datetime.utcnow().isoformat(),
                "prediction": prediction
            }
            
            self.data[key] = prediction_data
            logger.debug(f"✅ Set prediction for race {race_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error setting prediction: {str(e)}")
            return False
    
    async def get_prediction(self, race_id: str) -> Optional[Dict[str, Any]]:
        """Get prediction for a race"""
        try:
            key = f"race:{race_id}:predictions"
            return self.data.get(key)
            
        except Exception as e:
            logger.error(f"❌ Error getting prediction: {str(e)}")
            return None
    
    async def set_cache(self, key: str, data: Any, ttl: int = 3600) -> bool:
        """Set cached data"""
        try:
            self.data[key] = {
                "data": data,
                "timestamp": datetime.utcnow().isoformat(),
                "ttl": ttl
            }
            return True
            
        except Exception as e:
            logger.error(f"❌ Error setting cache: {str(e)}")
            return False
    
    async def get_cache(self, key: str) -> Optional[Any]:
        """Get cached data"""
        try:
            cached = self.data.get(key)
            if cached:
                return cached["data"]
            return None
            
        except Exception as e:
            logger.error(f"❌ Error getting cache: {str(e)}")
            return None
    
    async def delete_cache(self, key: str) -> bool:
        """Delete cached data"""
        try:
            if key in self.data:
                del self.data[key]
            return True
            
        except Exception as e:
            logger.error(f"❌ Error deleting cache: {str(e)}")
            return False
    
    async def get_redis_info(self) -> Dict[str, Any]:
        """Get mock Redis server information"""
        return {
            "redis_version": "mock-1.0.0",
            "connected_clients": len(self.subscribers),
            "used_memory": f"{len(str(self.data))} bytes",
            "keyspace": {"db0": {"keys": len(self.data)}},
            "uptime_in_seconds": 0
        }

class MockPubSub:
    """Mock Redis pub/sub client"""
    
    def __init__(self, redis_service):
        self.redis_service = redis_service
        self.subscribed_channels = []
    
    async def subscribe(self, channel: str):
        """Subscribe to a channel"""
        self.subscribed_channels.append(channel)
        logger.debug(f"✅ Subscribed to channel: {channel}")
    
    async def unsubscribe(self, channel: str):
        """Unsubscribe from a channel"""
        if channel in self.subscribed_channels:
            self.subscribed_channels.remove(channel)
        logger.debug(f"✅ Unsubscribed from channel: {channel}")
    
    async def listen(self):
        """Listen for messages on subscribed channels"""
        while True:
            for channel in self.subscribed_channels:
                if channel in self.redis_service.pubsub_channels:
                    messages = self.redis_service.pubsub_channels[channel]
                    if messages:
                        for message in messages:
                            yield {
                                "type": "message",
                                "channel": channel,
                                "data": json.dumps(message)
                            }
            await asyncio.sleep(0.1)  # Small delay to prevent busy waiting
