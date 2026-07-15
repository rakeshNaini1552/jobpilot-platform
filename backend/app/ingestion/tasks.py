"""Celery tasks for ingestion, wrapped in scheduled_runs bookkeeping."""
import structlog
from sqlalchemy import select

from app.core.db import worker_session
from app.scheduler.api import finish_run, record_run
from app.user.models import User
from app.worker.celery_app import celery_app

from .orchestrator import ingest_for_user

log = structlog.get_logger("ingestion.tasks")


def _run_ingestion(task_key: str, hours: int, limit: int) -> dict:
    with worker_session() as session:
        run_id = record_run(session, task_key)
    totals = {"jobs_found": 0, "jobs_new": 0, "users": 0}
    error = None
    try:
        from app.matching.service import score_jobs_for_user
        with worker_session() as session:
            users = session.scalars(select(User).where(User.is_active.is_(True))).all()
            for user in users:
                res = ingest_for_user(session, user.id, hours=hours, limit=limit)
                totals["jobs_found"] += res.jobs_found
                totals["jobs_new"] += res.jobs_new
                totals["users"] += 1
                score_jobs_for_user(session, user.id, res.new_job_ids)
        status = "SUCCESS"
    except Exception as e:  # noqa: BLE001
        error, status = str(e)[:500], "FAILED"
        log.exception("ingestion_task_failed", task=task_key)
    with worker_session() as session:
        finish_run(session, run_id, status, totals, error)
    return totals


@celery_app.task(name="app.ingestion.tasks.run_full_ingestion")
def run_full_ingestion() -> dict:
    """06:00 CT — wide daily sweep."""
    return _run_ingestion("ingest.full", hours=24, limit=50)


@celery_app.task(name="app.ingestion.tasks.run_incremental_ingestion")
def run_incremental_ingestion() -> dict:
    """Every 2h — only very recent postings."""
    return _run_ingestion("ingest.incremental", hours=3, limit=30)


@celery_app.task(name="app.ingestion.tasks.run_ingestion_for_user")
def run_ingestion_for_user(user_id: str, hours: int = 24, limit: int = 50) -> dict:
    """On-demand (triggered by POST /search-runs)."""
    with worker_session() as session:
        run_id = record_run(session, "ingest.ondemand")
    error, status = None, "SUCCESS"
    stats: dict = {}
    try:
        from app.matching.service import score_jobs_for_user
        with worker_session() as session:
            res = ingest_for_user(session, user_id, hours=hours, limit=limit)
            stats = res.as_dict()
            stats["scored"] = score_jobs_for_user(session, user_id, res.new_job_ids)
    except Exception as e:  # noqa: BLE001
        error, status = str(e)[:500], "FAILED"
    with worker_session() as session:
        finish_run(session, run_id, status, stats, error)
    return stats if not error else {"error": error}
