"""Notification Celery tasks — the 21:00 CT daily report."""
from datetime import UTC, datetime

import structlog
from sqlalchemy import select

from app.core.crypto import decrypt
from app.core.db import worker_session
from app.scheduler.api import finish_run, record_run
from app.user.models import User
from app.worker.celery_app import celery_app

from .channels import email_configured, send_email, send_webhook
from .models import Notification, NotificationSettings
from .report import build_daily_report

log = structlog.get_logger("notification.tasks")


def _deliver_report(session, user: User, settings: NotificationSettings | None) -> str:
    """Build + send one user's report across their enabled channels.
    Returns the aggregate delivery status."""
    report = build_daily_report(session, user)
    statuses = []

    email_enabled = settings.email_enabled if settings else True
    if email_enabled:
        note = Notification(user_id=user.id, channel="EMAIL",
                            template="daily_report", subject=report["subject"],
                            payload=report["payload"])
        if email_configured():
            ok, err = send_email(user.email, report["subject"], report["html"])
            note.status = "SENT" if ok else "FAILED"
            note.error = err
            note.sent_at = datetime.now(UTC) if ok else None
        else:
            note.status = "SKIPPED"
            note.error = "SMTP not configured"
        session.add(note)
        statuses.append(note.status)

    for channel, enc in (("SLACK", settings.slack_webhook_enc if settings else None),
                         ("DISCORD", settings.discord_webhook_enc if settings else None)):
        if not enc:
            continue
        summary = (f"JobPilot daily: {report['payload']['kpis'][0]['value']} new "
                   f"matches, {report['payload']['kpis'][1]['value']} applied. "
                   f"{report['payload']['app_url']}")
        ok, err = send_webhook(decrypt(enc), summary)
        session.add(Notification(
            user_id=user.id, channel=channel, template="daily_report",
            subject=report["subject"], payload={},
            status="SENT" if ok else "FAILED", error=err,
            sent_at=datetime.now(UTC) if ok else None))
        statuses.append("SENT" if ok else "FAILED")

    return ("SENT" if "SENT" in statuses else
            statuses[0] if statuses else "SKIPPED")


@celery_app.task(name="app.notification.tasks.send_daily_reports")
def send_daily_reports() -> dict:
    """21:00 America/Chicago — one report per active user."""
    with worker_session() as session:
        run_id = record_run(session, "report.daily")
    totals = {"sent": 0, "skipped": 0, "failed": 0}
    error = None
    try:
        with worker_session() as session:
            users = session.scalars(
                select(User).where(User.is_active.is_(True))).all()
            for user in users:
                settings = session.get(NotificationSettings, user.id)
                outcome = _deliver_report(session, user, settings)
                key = {"SENT": "sent", "SKIPPED": "skipped"}.get(outcome, "failed")
                totals[key] += 1
        status = "SUCCESS" if not totals["failed"] else "PARTIAL"
    except Exception as e:  # noqa: BLE001
        error, status = str(e)[:500], "FAILED"
        log.exception("daily_report_failed")
    with worker_session() as session:
        finish_run(session, run_id, status, totals, error)
    return totals
