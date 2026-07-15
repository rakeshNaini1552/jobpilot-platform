"""Profile endpoints — /users/me and preferences."""
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.api import CurrentUser
from app.auth.schemas import UserOut
from app.core.crypto import encrypt, mask
from app.core.db import get_session
from app.core.errors import Problem
from app.notification.api import NotificationSettings

from .models import Preferences
from .schemas import NotificationSettingsIO, PreferencesIO, UserPatch

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


def _settings_out(s: NotificationSettings) -> NotificationSettingsIO:
    # Column defaults apply at INSERT; a not-yet-persisted row has Nones.
    return NotificationSettingsIO(
        email_enabled=s.email_enabled if s.email_enabled is not None else True,
        daily_report_hour=(s.daily_report_hour
                           if s.daily_report_hour is not None else 21),
        slack_webhook=mask("configured") if s.slack_webhook_enc else "",
        discord_webhook=mask("configured") if s.discord_webhook_enc else "",
    )


@router.get("/me/notification-settings", response_model=NotificationSettingsIO)
async def get_notification_settings(user: CurrentUser, session: Session):
    settings = (await session.get(NotificationSettings, user.id)
                or NotificationSettings(user_id=user.id))
    return _settings_out(settings)


@router.put("/me/notification-settings", response_model=NotificationSettingsIO)
async def put_notification_settings(body: NotificationSettingsIO,
                                    user: CurrentUser, session: Session):
    settings = (await session.get(NotificationSettings, user.id)
                or NotificationSettings(user_id=user.id))
    settings.email_enabled = body.email_enabled
    settings.daily_report_hour = body.daily_report_hour
    # Webhooks are write-only: a non-empty, non-masked value replaces the
    # stored (encrypted) one; empty string clears it; masked value = no change.
    if body.slack_webhook and "***" not in body.slack_webhook:
        settings.slack_webhook_enc = encrypt(body.slack_webhook)
    elif body.slack_webhook == "":
        settings.slack_webhook_enc = None
    if body.discord_webhook and "***" not in body.discord_webhook:
        settings.discord_webhook_enc = encrypt(body.discord_webhook)
    elif body.discord_webhook == "":
        settings.discord_webhook_enc = None
    session.add(settings)
    await session.commit()
    await session.refresh(settings)
    return _settings_out(settings)
