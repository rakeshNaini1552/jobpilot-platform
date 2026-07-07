"""Profile endpoints — /users/me and preferences."""
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.api import CurrentUser
from app.auth.schemas import UserOut
from app.core.db import get_session
from app.core.errors import Problem

from .models import Preferences
from .schemas import PreferencesIO, UserPatch

router = APIRouter(prefix="/users", tags=["profile"])

Session = Annotated[AsyncSession, Depends(get_session)]


@router.get("/me", response_model=UserOut)
async def get_me(user: CurrentUser):
    return user


@router.patch("/me", response_model=UserOut)
async def update_me(body: UserPatch, user: CurrentUser, session: Session):
    if body.full_name is not None:
        user.full_name = body.full_name
    if body.timezone is not None:
        user.timezone = body.timezone
    session.add(user)
    await session.commit()
    return user


@router.get("/me/preferences", response_model=PreferencesIO)
async def get_preferences(user: CurrentUser, session: Session):
    prefs = await session.get(Preferences, user.id)
    if prefs is None:
        raise Problem(404, "Preferences not initialized", type_suffix="not-found")
    return prefs


@router.put("/me/preferences", response_model=PreferencesIO)
async def put_preferences(body: PreferencesIO, user: CurrentUser, session: Session):
    prefs = await session.get(Preferences, user.id) or Preferences(user_id=user.id)
    for field, value in body.model_dump().items():
        setattr(prefs, field, value)
    session.add(prefs)
    await session.commit()
    await session.refresh(prefs)
    return prefs
