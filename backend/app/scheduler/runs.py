"""Run bookkeeping for background tasks — every task execution is recorded
in scheduled_runs so the admin panel can answer "what did the robot do and
did it work?".

record_run first upserts the task key (disabled, cron 'manual') so ad-hoc
keys like 'ingest.ondemand' never violate the scheduled_runs FK.
"""
import json

from sqlalchemy import text
from sqlalchemy.orm import Session


def record_run(session: Session, task_key: str) -> int:
    session.execute(text(
        "INSERT INTO scheduled_tasks (key, cron, enabled, description) "
        "VALUES (:k, 'manual', false, 'ad-hoc task (auto-registered)') "
        "ON CONFLICT (key) DO NOTHING"), {"k": task_key})
    run_id = session.execute(text(
        "INSERT INTO scheduled_runs (task_key, status) "
        "VALUES (:k, 'RUNNING') RETURNING id"), {"k": task_key}).scalar()
    return run_id


def finish_run(session: Session, run_id: int, status: str,
               stats: dict, error: str | None = None) -> None:
    session.execute(text(
        "UPDATE scheduled_runs SET status = :s, finished_at = now(), "
        "stats = CAST(:st AS jsonb), error = :e WHERE id = :id"),
        {"s": status, "st": json.dumps(stats), "e": error, "id": run_id})
