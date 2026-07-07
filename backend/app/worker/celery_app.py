"""Celery application: broker/backend on Redis, beat schedule in Central Time.

Schedules mirror the seeded `scheduled_tasks` rows; the scheduler module
(Phase 10) syncs DB edits into beat. Task modules register via autodiscovery
against `app.<module>.tasks`.
"""
from celery import Celery
from celery.schedules import crontab

from app.core.settings import get_settings

settings = get_settings()

celery_app = Celery(
    "jobpilot",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    timezone=settings.default_timezone,       # America/Chicago
    enable_utc=True,
    task_acks_late=True,                      # re-deliver if a worker dies mid-task
    worker_prefetch_multiplier=1,             # fair scheduling for long scrape tasks
    task_default_queue="default",
    task_routes={
        "app.ingestion.*": {"queue": "ingest"},
        "app.ai.*": {"queue": "ai"},
        "app.generation.*": {"queue": "ai"},
        "app.notification.*": {"queue": "notify"},
    },
    beat_schedule={
        "ingest-full-daily": {
            "task": "app.ingestion.tasks.run_full_ingestion",
            "schedule": crontab(hour=6, minute=0),
        },
        "ingest-incremental": {
            "task": "app.ingestion.tasks.run_incremental_ingestion",
            "schedule": crontab(hour="8-18/2", minute=0),
        },
        "report-daily": {
            "task": "app.notification.tasks.send_daily_reports",
            "schedule": crontab(hour=21, minute=0),
        },
        "analytics-weekly": {
            "task": "app.analytics.tasks.run_weekly_analytics",
            "schedule": crontab(hour=18, minute=0, day_of_week=0),
        },
    },
)

celery_app.autodiscover_tasks([
    "app.ingestion", "app.ai", "app.matching", "app.generation",
    "app.application", "app.notification", "app.analytics", "app.scheduler",
])
