"""Append-only audit trail. Everything the platform does on the user's
behalf (logins, admin changes, automated applications, outbound messages)
goes through here."""
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

_INSERT = text(
    "INSERT INTO audit_events (user_id, actor, event_type, entity_type, entity_id, detail, ip) "
    "VALUES (:user_id, :actor, :event_type, :entity_type, :entity_id, CAST(:detail AS jsonb), "
    "CAST(:ip AS inet))"
)


def _clean_ip(ip: str | None) -> str | None:
    """Only store syntactically valid addresses (proxies/tests send names)."""
    if not ip:
        return None
    import ipaddress
    try:
        return str(ipaddress.ip_address(ip))
    except ValueError:
        return None


def _params(event_type: str, user_id: uuid.UUID | None, actor: str,
            entity_type: str | None, entity_id: str | None,
            detail: dict[str, Any] | None, ip: str | None) -> dict:
    import json
    return {
        "user_id": user_id, "actor": actor, "event_type": event_type,
        "entity_type": entity_type, "entity_id": entity_id,
        "detail": json.dumps(detail or {}), "ip": _clean_ip(ip),
    }


async def audit(session: AsyncSession, event_type: str, *,
                user_id: uuid.UUID | None = None, actor: str = "USER",
                entity_type: str | None = None, entity_id: str | None = None,
                detail: dict[str, Any] | None = None, ip: str | None = None) -> None:
    await session.execute(_INSERT, _params(event_type, user_id, actor,
                                           entity_type, entity_id, detail, ip))


def audit_sync(session: Session, event_type: str, *,
               user_id: uuid.UUID | None = None, actor: str = "SYSTEM",
               entity_type: str | None = None, entity_id: str | None = None,
               detail: dict[str, Any] | None = None) -> None:
    session.execute(_INSERT, _params(event_type, user_id, actor,
                                     entity_type, entity_id, detail, None))
