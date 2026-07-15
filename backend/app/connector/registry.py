"""Connector registry: maps connector_id → implementation, and loads each
connector's runtime config (enabled flag, rate limit, decrypted options)
from the connector_settings table."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.crypto import decrypt

from .connectors.aggregators import AdzunaConnector, JoobleConnector
from .connectors.ats import (
    AshbyConnector,
    GreenhouseConnector,
    LeverConnector,
    SmartRecruitersConnector,
)
from .connectors.dice import DiceConnector
from .connectors.public_feeds import RemoteOKConnector, RemotiveConnector
from .connectors.search_links import IndeedLinks, LinkedInLinks, MonsterLinks, ZipRecruiterLinks
from .models import ConnectorSetting
from .spi import ComplianceMode, ConnectorConfig

_FETCH_CONNECTORS = {
    c.descriptor.id: c for c in [
        GreenhouseConnector(), LeverConnector(), AshbyConnector(),
        SmartRecruitersConnector(), DiceConnector(),
        RemoteOKConnector(), RemotiveConnector(),
        AdzunaConnector(), JoobleConnector(),
    ]
}
_LINK_CONNECTORS = {
    c.descriptor.id: c for c in [
        LinkedInLinks(), IndeedLinks(), MonsterLinks(), ZipRecruiterLinks(),
    ]
}

# Field-level secret keys that are encrypted at rest in config.
_SECRET_KEYS = {"app_key", "api_key", "app_id"}


def all_descriptors() -> list:
    return [c.descriptor for c in
            (*_FETCH_CONNECTORS.values(), *_LINK_CONNECTORS.values())]


def get_fetch_connector(connector_id: str):
    return _FETCH_CONNECTORS.get(connector_id)


def get_link_connector(connector_id: str):
    return _LINK_CONNECTORS.get(connector_id)


def load_config(session: Session, connector_id: str,
                options: dict | None = None) -> ConnectorConfig:
    """Merge DB-level settings with per-watchlist options (e.g. ATS slug),
    decrypting any secret fields."""
    row = session.scalar(
        select(ConnectorSetting).where(ConnectorSetting.connector_id == connector_id))
    merged: dict = {}
    if row and row.config:
        for k, v in row.config.items():
            merged[k] = decrypt(v) if k in _SECRET_KEYS and isinstance(v, str) else v
    if options:
        merged.update(options)
    return ConnectorConfig(
        enabled=row.enabled if row else True,
        rate_limit_per_min=row.rate_limit_per_min if row else 30,
        options=merged,
    )


def is_enabled(session: Session, connector_id: str) -> bool:
    row = session.scalar(
        select(ConnectorSetting).where(ConnectorSetting.connector_id == connector_id))
    return bool(row.enabled) if row else False


def can_auto_apply(connector_id: str) -> bool:
    """Framework gate: automation only for OFFICIAL_API /
    USER_AUTHORIZED_AUTOMATION connectors that opt in."""
    c = _FETCH_CONNECTORS.get(connector_id)
    if not c:
        return False
    return (c.descriptor.supports_auto_apply and c.descriptor.compliance_mode
            in (ComplianceMode.OFFICIAL_API,
                ComplianceMode.USER_AUTHORIZED_AUTOMATION))
