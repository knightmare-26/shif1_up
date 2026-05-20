"""
Cache Service - Handles data caching for performance
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Optional, Dict
import os
from pathlib import Path

logger = logging.getLogger(__name__)

class CacheService:
    """Service for caching API responses and data"""
    
    def __init__(self, cache_dir: str = "./cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.memory_cache: Dict[str, Dict[str, Any]] = {}
        self.cache_stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0
        }
    
    async def initialize(self):
        """Initialize the cache service"""
        logger.info("🗄️ Initializing cache service...")
        
        # Load existing cache files
        await self._load_persistent_cache()
        
        # Start cleanup task
        asyncio.create_task(self._cleanup_expired_cache())
        
        logger.info("✅ Cache service initialized")
    
    async def get(self, key: str) -> Optional[Any]:
        """Get cached data by key"""
        try:
            # Check memory cache first
            if key in self.memory_cache:
                cache_entry = self.memory_cache[key]
                
                # Check if expired
                if datetime.utcnow() < cache_entry["expires_at"]:
                    self.cache_stats["hits"] += 1
                    logger.debug(f"📦 Cache hit for key: {key}")
                    return cache_entry["data"]
                else:
                    # Remove expired entry
                    del self.memory_cache[key]
            
            # Check persistent cache
            cache_file = self.cache_dir / f"{key}.json"
            if cache_file.exists():
                try:
                    with open(cache_file, 'r') as f:
                        cache_entry = json.load(f)
                    
                    # Check if expired
                    expires_at = datetime.fromisoformat(cache_entry["expires_at"])
                    if datetime.utcnow() < expires_at:
                        self.cache_stats["hits"] += 1
                        logger.debug(f"📦 Persistent cache hit for key: {key}")
                        
                        # Load into memory cache
                        self.memory_cache[key] = cache_entry
                        return cache_entry["data"]
                    else:
                        # Remove expired file
                        cache_file.unlink()
                        
                except (json.JSONDecodeError, KeyError, ValueError) as e:
                    logger.warning(f"⚠️ Invalid cache file {cache_file}: {e}")
                    cache_file.unlink()
            
            self.cache_stats["misses"] += 1
            logger.debug(f"❌ Cache miss for key: {key}")
            return None
            
        except Exception as e:
            logger.error(f"❌ Error getting cache for key {key}: {e}")
            self.cache_stats["misses"] += 1
            return None
    
    async def set(self, key: str, data: Any, ttl: int = 3600) -> bool:
        """Set cached data with TTL in seconds"""
        try:
            expires_at = datetime.utcnow() + timedelta(seconds=ttl)
            
            cache_entry = {
                "data": data,
                "created_at": datetime.utcnow().isoformat(),
                "expires_at": expires_at.isoformat(),
                "ttl": ttl
            }
            
            # Store in memory cache with datetime objects for easier comparison
            self.memory_cache[key] = {
                "data": data,
                "created_at": datetime.utcnow(),
                "expires_at": expires_at,
                "ttl": ttl
            }
            
            # Store in persistent cache
            cache_file = self.cache_dir / f"{key}.json"
            try:
                with open(cache_file, 'w') as f:
                    json.dump(cache_entry, f, default=str, indent=2)
            except Exception as e:
                logger.warning(f"⚠️ Failed to write persistent cache for {key}: {e}")
            
            self.cache_stats["sets"] += 1
            logger.debug(f"💾 Cached data for key: {key} (TTL: {ttl}s)")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error setting cache for key {key}: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete cached data by key"""
        try:
            # Remove from memory cache
            if key in self.memory_cache:
                del self.memory_cache[key]
            
            # Remove persistent cache file
            cache_file = self.cache_dir / f"{key}.json"
            if cache_file.exists():
                cache_file.unlink()
            
            self.cache_stats["deletes"] += 1
            logger.debug(f"🗑️ Deleted cache for key: {key}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error deleting cache for key {key}: {e}")
            return False
    
    async def clear_all(self) -> bool:
        """Clear all cached data"""
        try:
            # Clear memory cache
            self.memory_cache.clear()
            
            # Clear persistent cache files
            for cache_file in self.cache_dir.glob("*.json"):
                cache_file.unlink()
            
            # Reset stats
            self.cache_stats = {
                "hits": 0,
                "misses": 0,
                "sets": 0,
                "deletes": 0
            }
            
            logger.info("🧹 Cleared all cache data")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error clearing cache: {e}")
            return False
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total_requests = self.cache_stats["hits"] + self.cache_stats["misses"]
        hit_rate = (self.cache_stats["hits"] / total_requests * 100) if total_requests > 0 else 0
        
        # Count memory cache entries
        memory_entries = len(self.memory_cache)
        
        # Count persistent cache files
        persistent_entries = len(list(self.cache_dir.glob("*.json")))
        
        return {
            "memory_entries": memory_entries,
            "persistent_entries": persistent_entries,
            "total_entries": memory_entries + persistent_entries,
            "hits": self.cache_stats["hits"],
            "misses": self.cache_stats["misses"],
            "hit_rate": round(hit_rate, 2),
            "sets": self.cache_stats["sets"],
            "deletes": self.cache_stats["deletes"],
            "cache_dir": str(self.cache_dir)
        }
    
    async def _load_persistent_cache(self):
        """Load existing cache files into memory"""
        try:
            cache_files = list(self.cache_dir.glob("*.json"))
            loaded_count = 0
            
            for cache_file in cache_files:
                try:
                    with open(cache_file, 'r') as f:
                        cache_entry = json.load(f)
                    
                    # Check if not expired
                    expires_at = datetime.fromisoformat(cache_entry["expires_at"])
                    if datetime.utcnow() < expires_at:
                        key = cache_file.stem
                        self.memory_cache[key] = cache_entry
                        loaded_count += 1
                    else:
                        # Remove expired file
                        cache_file.unlink()
                        
                except (json.JSONDecodeError, KeyError, ValueError) as e:
                    logger.warning(f"⚠️ Invalid cache file {cache_file}: {e}")
                    cache_file.unlink()
            
            logger.info(f"📂 Loaded {loaded_count} cache entries from disk")
            
        except Exception as e:
            logger.error(f"❌ Error loading persistent cache: {e}")
    
    async def _cleanup_expired_cache(self):
        """Background task to clean up expired cache entries"""
        while True:
            try:
                await asyncio.sleep(300)  # Run every 5 minutes
                
                current_time = datetime.utcnow()
                expired_keys = []
                
                # Check memory cache
                for key, cache_entry in self.memory_cache.items():
                    expires_at = datetime.fromisoformat(cache_entry["expires_at"])
                    if current_time >= expires_at:
                        expired_keys.append(key)
                
                # Remove expired entries
                for key in expired_keys:
                    del self.memory_cache[key]
                
                # Check persistent cache files
                for cache_file in self.cache_dir.glob("*.json"):
                    try:
                        with open(cache_file, 'r') as f:
                            cache_entry = json.load(f)
                        
                        expires_at = datetime.fromisoformat(cache_entry["expires_at"])
                        if current_time >= expires_at:
                            cache_file.unlink()
                            
                    except (json.JSONDecodeError, KeyError, ValueError):
                        # Remove invalid files
                        cache_file.unlink()
                
                if expired_keys:
                    logger.debug(f"🧹 Cleaned up {len(expired_keys)} expired cache entries")
                    
            except Exception as e:
                logger.error(f"❌ Error in cache cleanup: {e}")
    
    async def cleanup(self):
        """Cleanup resources"""
        logger.info("🛑 Cleaning up cache service...")
        # Any cleanup tasks can be added here
        pass
