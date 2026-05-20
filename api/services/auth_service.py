"""
JWT Authentication Service
Handles token creation/verification and password hashing for the auth endpoints.
"""

import os
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

_DEFAULT_SECRET = "dev-secret-change-in-production"
SECRET_KEY = os.getenv("JWT_SECRET", _DEFAULT_SECRET)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

if SECRET_KEY == _DEFAULT_SECRET:
    import logging as _log
    _log.getLogger(__name__).warning(
        "JWT_SECRET is using the default dev value — set JWT_SECRET env var in production"
    )

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(data: Dict[str, Any]) -> str:
    to_encode = data.copy()
    to_encode["exp"] = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


def new_user_id() -> str:
    return str(uuid.uuid4())
