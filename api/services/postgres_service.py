"""
PostgreSQL service for user management via Supabase.
Handles all user auth storage — DuckDB is F1 data only.
"""

import json
import logging
from typing import Dict, Optional

import asyncpg

logger = logging.getLogger(__name__)


class PostgresService:
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.pool: Optional[asyncpg.Pool] = None

    async def initialize(self):
        self.pool = await asyncpg.create_pool(
            self.database_url,
            ssl="require",
            min_size=1,
            max_size=5,
        )
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id VARCHAR PRIMARY KEY,
                    username VARCHAR UNIQUE NOT NULL,
                    email VARCHAR UNIQUE NOT NULL,
                    hashed_password VARCHAR NOT NULL,
                    preferences JSONB DEFAULT '{}',
                    is_admin BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        logger.info("✅ PostgreSQL (Supabase) connected and users table ready")

    async def cleanup(self):
        if self.pool:
            await self.pool.close()

    async def create_user(self, user: Dict) -> bool:
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO users (id, username, email, hashed_password, preferences, is_admin)
                    VALUES ($1, $2, $3, $4, $5::jsonb, $6)
                    """,
                    user["id"],
                    user["username"],
                    user["email"],
                    user["hashed_password"],
                    json.dumps(user.get("preferences", {})),
                    user.get("is_admin", False),
                )
            return True
        except asyncpg.UniqueViolationError:
            return False
        except Exception as e:
            logger.error("❌ Error creating user: %s", e)
            return False

    def _row_to_dict(self, row: asyncpg.Record) -> Dict:
        result = dict(row)
        prefs = result.get("preferences")
        if isinstance(prefs, str):
            result["preferences"] = json.loads(prefs)
        elif prefs is None:
            result["preferences"] = {}
        return result

    async def get_user_by_username(self, username: str) -> Optional[Dict]:
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT id, username, email, hashed_password, preferences, is_admin, created_at "
                    "FROM users WHERE username = $1",
                    username,
                )
            return self._row_to_dict(row) if row else None
        except Exception as e:
            logger.error("❌ Error fetching user by username: %s", e)
            return None

    async def get_user_by_id(self, user_id: str) -> Optional[Dict]:
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT id, username, email, hashed_password, preferences, is_admin, created_at "
                    "FROM users WHERE id = $1",
                    user_id,
                )
            return self._row_to_dict(row) if row else None
        except Exception as e:
            logger.error("❌ Error fetching user by id: %s", e)
            return None

    async def update_user_preferences(self, user_id: str, preferences: Dict) -> bool:
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE users SET preferences = $1::jsonb WHERE id = $2",
                    json.dumps(preferences),
                    user_id,
                )
            return True
        except Exception as e:
            logger.error("❌ Error updating user preferences: %s", e)
            return False
