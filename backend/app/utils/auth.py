"""Authentication utilities: JWT token creation and verification.

Adapted from FastAPI-LangGraph template.
"""

import os
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt

from app.core.config import settings
from app.core.logging import logger
from app.models.schemas import Token
from app.utils.sanitization import sanitize_string


def _load_rsa_keys(settings_obj):
    """Загрузка RSA-ключей с graceful fallback на HS256."""
    private_key_path = settings_obj.JWT_PRIVATE_KEY_PATH
    public_key_path = settings_obj.JWT_PUBLIC_KEY_PATH

    if os.path.exists(private_key_path) and os.path.exists(public_key_path):
        with open(private_key_path, "r") as f:
            private_key = f.read()
        with open(public_key_path, "r") as f:
            public_key = f.read()
        return private_key, public_key, "RS256"

    # Fallback на HS256 для обратной совместимости
    return settings_obj.JWT_SECRET_KEY, settings_obj.JWT_SECRET_KEY, "HS256"


def create_access_token(
    user_id: int,
    email: str,
    role: str = "viewer",
    expires_delta: Optional[timedelta] = None,
) -> Token:
    """Create a JWT access token.

    Args:
        user_id: User's database ID.
        email: User's email.
        role: User's RBAC role.
        expires_delta: Optional custom expiration.

    Returns:
        Token with access_token, type, and expiration.
    """
    private_key, _, algorithm = _load_rsa_keys(settings)
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(days=settings.JWT_ACCESS_TOKEN_EXPIRE_DAYS))

    to_encode = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }

    encoded_jwt = jwt.encode(to_encode, private_key, algorithm=algorithm)
    logger.info("token_created", user_id=user_id, expires_at=expire.isoformat())

    return Token(access_token=encoded_jwt, expires_at=expire)


def verify_token(token: str) -> Optional[dict]:
    """Verify a JWT token and return the payload.

    Args:
        token: JWT token string.

    Returns:
        Dict with user_id, email, role if valid; None otherwise.

    Raises:
        ValueError: If token format is invalid.
    """
    if not token or not isinstance(token, str):
        raise ValueError("Token must be a non-empty string")

    if not re.match(r"^[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+$", token):
        raise ValueError("Invalid token format")

    _, public_key, algorithm = _load_rsa_keys(settings)

    try:
        payload = jwt.decode(token, public_key, algorithms=[algorithm, "HS256"])
        user_id = payload.get("sub")
        if user_id is None:
            return None
        return {
            "user_id": int(user_id),
            "email": payload.get("email", ""),
            "role": payload.get("role", "viewer"),
        }
    except jwt.PyJWTError as e:
        logger.warning("token_verification_failed", error=str(e))
        return None
