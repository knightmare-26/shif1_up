"""
Redis Service for Live State Management and Pub/Sub
Handles Redis operations for real-time F1 data
"""

import redis.asyncio as redis
import json
import logging
from typing import Dict, Any, Optional, AsyncGenerator
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class RedisService:
    """Service for Redis operations and live state management"""
    
    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self.redis_client = None
        self.pubsub = None
        
    async def initialize(self):
        """Initialize Redis connection"""
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            
            # Test connection
            await self.redis_client.ping()
            
            logger.info(f"✅ Redis connected at {self.redis_url}")
            
        except Exception as e:
            logger.error(f"❌ Error connecting to Redis: {str(e)}")
            raise
    
    async def cleanup(self):
        """Cleanup Redis connection"""
        try:
            if self.pubsub:
                await self.pubsub.close()
            if self.redis_client:
                await self.redis_client.close()
            logger.info("✅ Redis cleanup completed")
        except Exception as e:
            logger.error(f"❌ Error during Redis cleanup: {str(e)}")
    
    def get_pubsub(self):
        """Get Redis pub/sub client"""
        if not self.pubsub:
            self.pubsub = self.redis_client.pubsub()
        return self.pubsub
    
    async def set_live_state(self, race_id: str, state: Dict[str, Any], ttl: int = 3600) -> bool:
        """Set live state for a race"""
        try:
            key = f"race:{race_id}:state"
            state_data = {
                "race_id": race_id,
                "timestamp": datetime.utcnow().isoformat(),
                "state": state
            }
            
            await self.redis_client.setex(
                key, 
                ttl, 
                json.dumps(state_data)
            )
            
            logger.debug(f"✅ Set live state for race {race_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error setting live state: {str(e)}")
            return False
    
    async def get_live_state(self, race_id: str) -> Optional[Dict[str, Any]]:
        """Get live state for a race"""
        try:
            key = f"race:{race_id}:state"
            state_data = await self.redis_client.get(key)
            
            if state_data:
                return json.loads(state_data)
            return None
            
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
            
            await self.redis_client.publish(
                channel, 
                json.dumps(update_data)
            )
            
            logger.debug(f"✅ Published update for race {race_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error publishing update: {str(e)}")
            return False
    
    async def subscribe_to_race(self, race_id: str) -> AsyncGenerator[Dict[str, Any], None]:
        """Subscribe to live updates for a race"""
        try:
            channel = f"race:{race_id}:updates"
            pubsub = self.get_pubsub()
            
            await pubsub.subscribe(channel)
            
            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        yield data
                    except json.JSONDecodeError:
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
            
            await self.redis_client.setex(
                key, 
                ttl, 
                json.dumps(prediction_data)
            )
            
            logger.debug(f"✅ Set prediction for race {race_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error setting prediction: {str(e)}")
            return False
    
    async def get_prediction(self, race_id: str) -> Optional[Dict[str, Any]]:
        """Get prediction for a race"""
        try:
            key = f"race:{race_id}:predictions"
            prediction_data = await self.redis_client.get(key)
            
            if prediction_data:
                return json.loads(prediction_data)
            return None
            
        except Exception as e:
            logger.error(f"❌ Error getting prediction: {str(e)}")
            return None
    
    async def set_cache(self, key: str, data: Any, ttl: int = 3600) -> bool:
        """Set cached data"""
        try:
            await self.redis_client.setex(
                key, 
                ttl, 
                json.dumps(data, default=str)
            )
            return True
            
        except Exception as e:
            logger.error(f"❌ Error setting cache: {str(e)}")
            return False
    
    async def get_cache(self, key: str) -> Optional[Any]:
        """Get cached data"""
        try:
            data = await self.redis_client.get(key)
            if data:
                return json.loads(data)
            return None
            
        except Exception as e:
            logger.error(f"❌ Error getting cache: {str(e)}")
            return None
    
    async def delete_cache(self, key: str) -> bool:
        """Delete cached data"""
        try:
            await self.redis_client.delete(key)
            return True
            
        except Exception as e:
            logger.error(f"❌ Error deleting cache: {str(e)}")
            return False
    
    async def get_race_keys(self, pattern: str = "race:*:state") -> List[str]:
        """Get all race keys matching pattern"""
        try:
            keys = await self.redis_client.keys(pattern)
            return keys
            
        except Exception as e:
            logger.error(f"❌ Error getting race keys: {str(e)}")
            return []
    
    async def get_redis_info(self) -> Dict[str, Any]:
        """Get Redis server information"""
        try:
            info = await self.redis_client.info()
            return {
                "redis_version": info.get("redis_version"),
                "connected_clients": info.get("connected_clients"),
                "used_memory": info.get("used_memory_human"),
                "keyspace": info.get("keyspace", {}),
                "uptime_in_seconds": info.get("uptime_in_seconds")
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting Redis info: {str(e)}")
            return {}
