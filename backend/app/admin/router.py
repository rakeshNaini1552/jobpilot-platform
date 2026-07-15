"""Admin endpoints — schedules, run history, connectors. ADMIN role only."""
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.api import AdminUser
from app.common.audit import audit
from app.connector.api import ConnectorSetting
from app.core.db import get_session
from app.core.errors import Problem
from app.scheduler.api import ScheduledRun, ScheduledTask

router = APIRouter(prefix="/admin", tags=["admin"])

Session = Annotated[AsyncSession, Depends(get_session)]


# ---------------------------------------------------------------- schedules
class ScheduleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    key: str
    cron: str
    timezone: str
    enabled: bool
    description: str | None = None


class SchedulePatch(BaseModel):
    cron: str | None = Field(default=None, min_length=9, max_length=64)
    enabled: bool | None = None


@router.get("/schedules", response_model=list[ScheduleOut])
async def list_schedules(session: Session, admin: AdminUser):
    return (await session.scalars(
        select(ScheduledTask).order_by(ScheduledTask.key))).all()


@router.patch("/schedules/{task_key}", response_model=ScheduleOut)
async def update_schedule(task_key: str, body: SchedulePatch,
                          session: Session, admin: AdminUser):
    task = await session.scalar(
        select(ScheduledTask).where(ScheduledTask.key == task_key))
    if task is None:
        raise Problem(404, "Unknown schedule", type_suffix="not-found")
    if body.cron is not None:
        if len(body.cron.split()) != 5:
            raise Problem(422, "Invalid cron expression",
                          "Expected 5 space-separated fields.",
                          type_suffix="bad-cron")
        task.cron = body.cron
    if body.enabled is not None:
        task.enabled = body.enabled
    await audit(session, "admin.schedule_updated", user_id=admin.id,
                entity_type="scheduled_task", entity_id=task_key,
                detail=body.model_dump(exclude_none=True))
    await session.commit()
    return task


@router.post("/schedules/{task_key}/run", status_code=202)
async def run_schedule_now(task_key: str, session: Session, admin: AdminUser):
    task = await session.scalar(
        select(ScheduledTask).where(ScheduledTask.key == task_key))
    if task is None:
        raise Problem(404, "Unknown schedule", type_suffix="not-found")
    celery_task_names = {
        "ingest.full": "app.ingestion.tasks.run_full_ingestion",
        "ingest.incremental": "app.ingestion.tasks.run_incremental_ingestion",
        "report.daily": "app.notification.tasks.send_daily_reports",
        "analytics.weekly": "app.analytics.tasks.run_weekly_analytics",
    }
    name = celery_task_names.get(task_key)
    if name is None:
        raise Problem(409, "Schedule has no runnable task", type_suffix="not-runnable")
    try:
        from app.worker.celery_app import celery_app
        async_result = celery_app.send_task(name)
    except Exception:
        raise Problem(503, "Task queue unavailable",
                      "Start the Celery worker/Redis to trigger tasks.",
                      type_suffix="queue-unavailable") from None
    await audit(session, "admin.schedule_triggered", user_id=admin.id,
                entity_type="scheduled_task", entity_id=task_key)
    await session.commit()
    return {"queued": True, "celery_id": async_result.id}


# ---------------------------------------------------------------- run history
class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    task_key: str
    status: str
    started_at: object
    finished_at: object | None = None
    stats: dict = {}
    error: str | None = None


@router.get("/runs", response_model=list[RunOut])
async def list_runs(session: Session, admin: AdminUser,
                    task_key: str | None = None,
                    limit: int = Query(default=50, le=200)):
    stmt = select(ScheduledRun).order_by(ScheduledRun.started_at.desc()).limit(limit)
    if task_key:
        stmt = stmt.where(ScheduledRun.task_key == task_key)
    return (await session.scalars(stmt)).all()


# ---------------------------------------------------------------- connectors
class ConnectorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    connector_id: str
    display_name: str
    compliance_mode: str
    enabled: bool
    rate_limit_per_min: int


class ConnectorPatch(BaseModel):
    enabled: bool | None = None
    rate_limit_per_min: int | None = Field(default=None, ge=0, le=600)


@router.get("/connectors", response_model=list[ConnectorOut])
async def list_connectors(session: Session, admin: AdminUser):
    return (await session.scalars(
        select(ConnectorSetting).order_by(ConnectorSetting.connector_id))).all()


@router.patch("/connectors/{connector_id}", response_model=ConnectorOut)
async def update_connector(connector_id: str, body: ConnectorPatch,
                           session: Session, admin: AdminUser):
    row = await session.scalar(select(ConnectorSetting).where(
        ConnectorSetting.connector_id == connector_id))
    if row is None:
        raise Problem(404, "Unknown connector", type_suffix="not-found")
    if body.enabled is not None:
        row.enabled = body.enabled
    if body.rate_limit_per_min is not None:
        row.rate_limit_per_min = body.rate_limit_per_min
    await audit(session, "admin.connector_updated", user_id=admin.id,
                entity_type="connector", entity_id=connector_id,
                detail=body.model_dump(exclude_none=True))
    await session.commit()
    return row
