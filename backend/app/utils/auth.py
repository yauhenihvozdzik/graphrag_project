"""Authentication utilities: JWT token creation and verification.

Adapted from FastAPI-LangGraph template.
"""

import re
from datetime import UTC, datetime, timedelta
from typing import Optional

from jose import JWTError, jwt

from app.core.config import settings
from app.core.logging import logger
from app.models.schemas import Token
from app.utils.sanitization import sanitize_string


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
    expire = datetime.now(UTC) + (expires_delta or timedelta(days=settings.JWT_ACCESS_TOKEN_EXPIRE_DAYS))

    to_encode = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "exp": expire,
        "iat": datetime.now(UTC),
    }

    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
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

    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            return None
        return {
            "user_id": int(user_id),
            "email": payload.get("email", ""),
            "role": payload.get("role", "viewer"),
        }
    except JWTError as e:
        logger.warning("token_verification_failed", error=str(e))
        return None
