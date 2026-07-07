"""Celery tasks for ingestion, wrapped in scheduled_runs bookkeeping."""
from datetime import datetime

import structlog
from sqlalchemy import select

from app.core.db import worker_session
from app.user.models import User
from app.worker.celery_app import celery_app

from .orchestrator import ingest_for_user

log = structlog.get_logger("ingestion.tasks")


def _record_run(session, task_key: str):
    from sqlalchemy import text
    row = session.execute(
        text("INSERT INTO scheduled_runs (task_key, status) "
             "VALUES (:k, 'RUNNING') RETURNING id"), {"k": task_key}).scalar()
    return row


def _finish_run(session, run_id: int, status: str, stats: dict, error: str | None = None):
    import json

    from sqlalchemy import text
    session.execute(
        text("UPDATE scheduled_runs SET status=:s, finished_at=now(), "
             "stats=CAST(:st AS jsonb), error=:e WHERE id=:id"),
        {"s": status, "st": json.dumps(stats), "e": error, "id": run_id})


def _run_ingestion(task_key: str, hours: int, limit: int) -> dict:
    with worker_session() as session:
        run_id = _record_run(session, task_key)
        session.commit()
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
        _finish_run(session, run_id, status, totals, error)
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
        run_id = _record_run(session, "ingest.ondemand")
        session.commit()
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
        _finish_run(session, run_id, status, stats, error)
    return stats or {"error": error, "at": datetime.now().isoformat()}
