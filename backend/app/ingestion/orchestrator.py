"""Ingestion orchestrator: builds a JobQuery from a user's preferences, runs
every enabled fetch connector (global + the user's ATS watchlist), normalizes
and dedupes results, and reports counters.

Pure function of (session, user) so it's callable from Celery tasks, the
on-demand API endpoint, and tests alike."""
from dataclasses import dataclass, field

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connector import registry
from app.connector.models import CompanyWatchlist, ConnectorSetting
from app.connector.spi import ComplianceMode, JobQuery, RawPosting
from app.user.models import Preferences

from .normalize import upsert_job

log = structlog.get_logger("ingestion")


@dataclass
class IngestionResult:
    jobs_found: int = 0
    jobs_new: int = 0
    connectors_run: list[str] = field(default_factory=list)
    connectors_failed: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "jobs_found": self.jobs_found, "jobs_new": self.jobs_new,
            "connectors_run": self.connectors_run,
            "connectors_failed": self.connectors_failed,
        }


def build_query(prefs: Preferences | None, hours: int, limit: int) -> JobQuery:
    if prefs is None:
        return JobQuery(terms=["software engineer"], posted_within_hours=hours,
                        limit=limit)
    location = None
    if prefs.locations:
        first = prefs.locations[0]
        location = ", ".join(x for x in (first.get("city"), first.get("state"))
                             if x) or None
    remote = "REMOTE" in (prefs.workplace_types or [])
    return JobQuery(
        terms=list(prefs.desired_titles or ["software engineer"]),
        location=location,
        country=(prefs.countries or ["US"])[0][:2].upper(),
        remote=remote or None,
        employment_types=list(prefs.employment_types or []),
        posted_within_hours=hours,
        limit=limit,
    )


def _global_fetch_connectors(session: Session) -> list[str]:
    """Enabled fetch connectors that need no per-company slug (Dice, aggregators)."""
    rows = session.scalars(
        select(ConnectorSetting).where(
            ConnectorSetting.enabled.is_(True),
            ConnectorSetting.compliance_mode.in_(
                [ComplianceMode.PUBLIC_FEED.value, ComplianceMode.OFFICIAL_API.value]))
    ).all()
    ids = []
    for row in rows:
        c = registry.get_fetch_connector(row.connector_id)
        # ATS connectors require a slug and run via the watchlist, not globally.
        if c and not c.is_configured(registry.ConnectorConfig()):
            if row.connector_id in ("greenhouse", "lever", "ashby", "smartrecruiters"):
                continue
            # aggregators need keys — skip silently if unconfigured
            cfg = registry.load_config(session, row.connector_id)
            if not c.is_configured(cfg):
                continue
            ids.append(row.connector_id)
        elif c:
            ids.append(row.connector_id)
    return ids


def _run_connector(session: Session, connector_id: str, query: JobQuery,
                   options: dict | None, result: IngestionResult) -> None:
    connector = registry.get_fetch_connector(connector_id)
    if connector is None:
        return
    cfg = registry.load_config(session, connector_id, options)
    if not cfg.enabled or not connector.is_configured(cfg):
        return
    try:
        postings: list[RawPosting] = connector.search(query, cfg)
    except Exception as e:  # noqa: BLE001
        log.warning("connector_failed", connector=connector_id, error=str(e)[:200])
        result.connectors_failed.append(connector_id)
        return
    result.connectors_run.append(connector_id)
    for posting in postings:
        if not posting.title or not posting.url:
            continue
        result.jobs_found += 1
        _, is_new = upsert_job(session, posting)
        if is_new:
            result.jobs_new += 1


def ingest_for_user(session: Session, user_id, *, hours: int = 24,
                    limit: int = 50) -> IngestionResult:
    prefs = session.get(Preferences, user_id)
    query = build_query(prefs, hours, limit)
    result = IngestionResult()

    for connector_id in _global_fetch_connectors(session):
        _run_connector(session, connector_id, query, None, result)

    # Per-user ATS watchlist (staffing firms & target companies by slug).
    watch = session.scalars(
        select(CompanyWatchlist).where(
            CompanyWatchlist.enabled.is_(True),
            (CompanyWatchlist.user_id == user_id) | (CompanyWatchlist.user_id.is_(None)))
    ).all()
    for entry in watch:
        if registry.is_enabled(session, entry.connector_id):
            _run_connector(session, entry.connector_id, query, entry.config, result)

    session.flush()
    log.info("ingestion_complete", user_id=str(user_id), **result.as_dict())
    return result
