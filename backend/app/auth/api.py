"""Public facade of the auth module: request-scoped identity dependencies.

Usage in any router:
    user: CurrentUser            — 401 unless a valid access token is presented
    admin: AdminUser             — 403 unless the user has the ADMIN role
"""
import uuid
from typing import Annotated

import jwt as pyjwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.errors import Problem
from app.core.security import decode_access_token
from app.user.models import User

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    if credentials is None:
        raise Problem(401, "Not authenticated", type_suffix="unauthenticated")
    try:
        claims = decode_access_token(credentials.credentials)
        user_id = uuid.UUID(claims["sub"])
    except (pyjwt.PyJWTError, KeyError, ValueError) as e:
        raise Problem(401, "Invalid or expired token",
                      type_suffix="bad-token") from e
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise Problem(401, "Account not available", type_suffix="account-disabled")
    return user


async def require_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.role != "ADMIN":
        raise Problem(403, "Admin role required", type_suffix="forbidden")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(require_admin)]
