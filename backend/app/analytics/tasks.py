"""Weekly analytics snapshot — Sundays 18:00 CT. Materializes each user's
dashboard metrics into analytics_snapshots for trend history."""
import json

import structlog
from sqlalchemy import select, text

from app.core.db import worker_session
from app.scheduler.api import finish_run, record_run
from app.user.models import User
from app.worker.celery_app import celery_app

log = structlog.get_logger("analytics.tasks")


def snapshot_user_metrics(session, user_id) -> dict:
    """Sync flavor of the dashboard aggregates (worker-side)."""
    funnel = dict(session.execute(text(
        "SELECT status, count(*) FROM applications "
        "WHERE user_id = :uid AND deleted_at IS NULL GROUP BY status"),
        {"uid": str(user_id)}).all())
    jobs_found = session.execute(text(
        "SELECT count(*) FROM jobs WHERE status = 'ACTIVE'")).scalar() or 0
    avg_score = session.execute(text(
        "SELECT round(avg(overall), 1) FROM match_scores WHERE user_id = :uid"),
        {"uid": str(user_id)}).scalar()
    metrics = {"funnel": funnel, "jobs_found": jobs_found,
               "avg_match_score": float(avg_score) if avg_score else None}
    session.execute(text(
        "INSERT INTO analytics_snapshots (user_id, snapshot_date, metrics) "
        "VALUES (:uid, CURRENT_DATE, CAST(:m AS jsonb)) "
        "ON CONFLICT (user_id, snapshot_date) "
        "DO UPDATE SET metrics = EXCLUDED.metrics"),
        {"uid": str(user_id), "m": json.dumps(metrics)})
    return metrics


@celery_app.task(name="app.analytics.tasks.run_weekly_analytics")
def run_weekly_analytics() -> dict:
    with worker_session() as session:
        run_id = record_run(session, "analytics.weekly")
    totals = {"users": 0}
    error = None
    try:
        with worker_session() as session:
            for user in session.scalars(
                    select(User).where(User.is_active.is_(True))).all():
                snapshot_user_metrics(session, user.id)
                totals["users"] += 1
        status = "SUCCESS"
    except Exception as e:  # noqa: BLE001
        error, status = str(e)[:500], "FAILED"
        log.exception("weekly_analytics_failed")
    with worker_session() as session:
        finish_run(session, run_id, status, totals, error)
    return totals
