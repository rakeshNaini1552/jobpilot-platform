"""Password hashing (bcrypt) and JWT access tokens (HS256)."""
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from .settings import get_settings

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def create_access_token(user_id: uuid.UUID, role: str) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    claims = {
        "sub": str(user_id),
        "role": role,
        "type": "access",
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + timedelta(seconds=settings.jwt_access_ttl_seconds),
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """Raises jwt.PyJWTError on any problem (expiry, signature, malformed)."""
    claims = jwt.decode(token, get_settings().jwt_secret, algorithms=[ALGORITHM])
    if claims.get("type") != "access":
        raise jwt.InvalidTokenError("not an access token")
    return claims


def create_state_token(payload: dict[str, Any], ttl_seconds: int = 600) -> str:
    """Short-lived signed token for OAuth state (no server-side session)."""
    now = datetime.now(UTC)
    claims = {**payload, "type": "state", "iat": now,
              "exp": now + timedelta(seconds=ttl_seconds)}
    return jwt.encode(claims, get_settings().jwt_secret, algorithm=ALGORITHM)


def decode_state_token(token: str) -> dict[str, Any]:
    claims = jwt.decode(token, get_settings().jwt_secret, algorithms=[ALGORITHM])
    if claims.get("type") != "state":
        raise jwt.InvalidTokenError("not a state token")
    return claims
