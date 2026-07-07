"""Authentication use cases: register, login, refresh rotation with reuse
detection, logout, password reset. Every security-relevant event is audited."""
import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.audit import _clean_ip, audit
from app.core.errors import Problem
from app.core.security import create_access_token, hash_password, verify_password
from app.core.settings import get_settings
from app.notification.api import send_password_reset
from app.user.models import Preferences, User

from .models import PasswordResetToken, RefreshToken

log = structlog.get_logger("auth")

RESET_TOKEN_TTL_MINUTES = 30


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _new_opaque_token() -> str:
    return secrets.token_urlsafe(48)


async def _issue_pair(session: AsyncSession, user: User,
                      ip: str | None = None, user_agent: str | None = None) -> dict:
    raw_refresh = _new_opaque_token()
    session.add(RefreshToken(
        user_id=user.id,
        token_hash=_hash_token(raw_refresh),
        expires_at=datetime.now(UTC) + timedelta(days=get_settings().refresh_ttl_days),
        created_ip=_clean_ip(ip),
        user_agent=(user_agent or "")[:400] or None,
    ))
    await session.flush()
    return {
        "access_token": create_access_token(user.id, user.role),
        "refresh_token": raw_refresh,
        "expires_in": get_settings().jwt_access_ttl_seconds,
        "user": user,
    }


async def register(session: AsyncSession, email: str, password: str,
                   full_name: str, ip: str | None = None) -> dict:
    existing = await session.scalar(select(User).where(User.email == email.lower()))
    if existing:
        raise Problem(409, "Email already registered", type_suffix="email-taken")

    # The very first account becomes ADMIN (single-owner bootstrap; later
    # signups are USERs managed from the admin panel).
    first_user = (await session.scalar(select(User.id).limit(1))) is None
    user = User(email=email.lower(), password_hash=hash_password(password),
                full_name=full_name, role="ADMIN" if first_user else "USER")
    session.add(user)
    await session.flush()
    session.add(Preferences(user_id=user.id))
    await audit(session, "auth.register", user_id=user.id, ip=ip,
                detail={"role": user.role})
    return await _issue_pair(session, user, ip)


async def login(session: AsyncSession, email: str, password: str,
                ip: str | None = None, user_agent: str | None = None) -> dict:
    user = await session.scalar(select(User).where(User.email == email.lower()))
    if not user or not user.password_hash or not verify_password(password, user.password_hash):
        await audit(session, "auth.login_failed", ip=ip, detail={"email": email.lower()})
        await session.commit()  # audit must survive the 401 rollback
        raise Problem(401, "Invalid credentials", type_suffix="bad-credentials")
    if not user.is_active:
        raise Problem(401, "Account disabled", type_suffix="account-disabled")
    await audit(session, "auth.login", user_id=user.id, ip=ip)
    return await _issue_pair(session, user, ip, user_agent)


async def refresh(session: AsyncSession, raw_refresh: str,
                  ip: str | None = None) -> dict:
    token = await session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == _hash_token(raw_refresh)))
    if not token:
        raise Problem(401, "Invalid refresh token", type_suffix="bad-refresh")

    now = datetime.now(UTC)
    if token.replaced_by is not None or token.revoked_at is not None:
        # Reuse of a rotated/revoked token ⇒ the token was likely stolen.
        # Revoke every live session for this user and alert via audit log.
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == token.user_id,
                   RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now))
        await audit(session, "auth.refresh_reuse_detected", user_id=token.user_id,
                    actor="SYSTEM", ip=ip)
        await session.commit()  # revocations must survive the 401 rollback
        log.warning("refresh_token_reuse", user_id=str(token.user_id))
        raise Problem(401, "Refresh token reuse detected; all sessions revoked",
                      type_suffix="refresh-reuse")
    if token.expires_at < now:
        raise Problem(401, "Refresh token expired", type_suffix="refresh-expired")

    user = await session.get(User, token.user_id)
    if not user or not user.is_active:
        raise Problem(401, "Account disabled", type_suffix="account-disabled")

    pair = await _issue_pair(session, user, ip)
    new_token = await session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == _hash_token(pair["refresh_token"])))
    token.revoked_at = now
    token.replaced_by = new_token.id
    return pair


async def logout(session: AsyncSession, raw_refresh: str | None,
                 user_id: uuid.UUID, ip: str | None = None) -> None:
    if raw_refresh:
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.token_hash == _hash_token(raw_refresh),
                   RefreshToken.user_id == user_id)
            .values(revoked_at=datetime.now(UTC)))
    await audit(session, "auth.logout", user_id=user_id, ip=ip)


async def forgot_password(session: AsyncSession, email: str) -> None:
    """Always succeeds outwardly (no account enumeration)."""
    user = await session.scalar(select(User).where(User.email == email.lower()))
    if not user:
        return
    raw = _new_opaque_token()
    session.add(PasswordResetToken(
        user_id=user.id, token_hash=_hash_token(raw),
        expires_at=datetime.now(UTC) + timedelta(minutes=RESET_TOKEN_TTL_MINUTES)))
    await audit(session, "auth.password_reset_requested", user_id=user.id)
    send_password_reset(user.email, raw)


async def reset_password(session: AsyncSession, raw_token: str,
                         new_password: str) -> None:
    token = await session.scalar(
        select(PasswordResetToken)
        .where(PasswordResetToken.token_hash == _hash_token(raw_token)))
    now = datetime.now(UTC)
    if not token or token.used_at is not None or token.expires_at < now:
        raise Problem(400, "Invalid or expired reset token", type_suffix="bad-reset-token")

    user = await session.get(User, token.user_id)
    user.password_hash = hash_password(new_password)
    token.used_at = now
    # New password ⇒ every existing session is revoked.
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now))
    await audit(session, "auth.password_reset", user_id=user.id)
