"""Application tracker endpoints — ATS-style pipeline with event-sourced
status history."""
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from app.auth.api import CurrentUser
from app.common.audit import audit
from app.common.pagination import Page, PageParams, page_params
from app.connector.models import Job
from app.connector.schemas import JobOut
from app.core.db import get_session
from app.core.errors import Problem

from .models import Application, ApplicationEvent
from .schemas import (
    ApplicationEventOut,
    ApplicationOut,
    ApplicationPage,
    ChangeStatusIn,
    CreateApplicationIn,
    UpdateApplicationIn,
)

router = APIRouter(prefix="/applications", tags=["applications"])

Session = Annotated[AsyncSession, Depends(get_session)]


def _to_out(app_row: Application, job: Job) -> ApplicationOut:
    out = ApplicationOut.model_validate(
        {**app_row.__dict__, "job": JobOut.model_validate(job)})
    return out


async def _owned(session, user, application_id) -> Application:
    row = await session.get(Application, application_id)
    if row is None or row.user_id != user.id or row.deleted_at is not None:
        raise Problem(404, "Application not found", type_suffix="not-found")
    return row


@router.get("", response_model=ApplicationPage)
async def list_applications(
    session: Session, user: CurrentUser,
    params: Annotated[PageParams, Depends(page_params)],
    status: str | None = None,
):
    base = (select(Application, Job).join(Job, Application.job_id == Job.id)
            .where(Application.user_id == user.id,
                   Application.deleted_at.is_(None)))
    if status:
        base = base.where(Application.status == status)
    total = await session.scalar(
        select(func.count()).select_from(base.subquery()))
    rows = (await session.execute(
        base.order_by(Application.updated_at.desc())
        .offset((params.page - 1) * params.size).limit(params.size))).all()
    return Page.of([_to_out(a, j) for a, j in rows], params, total or 0)


@router.post("", response_model=ApplicationOut, status_code=201)
async def create_application(body: CreateApplicationIn, session: Session,
                             user: CurrentUser):
    job = await session.get(Job, body.job_id)
    if job is None:
        raise Problem(404, "Job not found", type_suffix="not-found")
    exists = await session.scalar(
        select(Application).where(Application.user_id == user.id,
                                  Application.job_id == body.job_id))
    if exists:
        raise Problem(409, "Job already tracked", type_suffix="already-tracked",
                      application_id=str(exists.id))
    row = Application(user_id=user.id, job_id=body.job_id, status=body.status,
                      notes=body.notes,
                      applied_at=datetime.now(UTC) if body.status == "APPLIED" else None)
    session.add(row)
    await session.flush()
    session.add(ApplicationEvent(application_id=row.id, from_status=None,
                                 to_status=body.status))
    await audit(session, "tracker.created", user_id=user.id,
                entity_type="application", entity_id=str(row.id))
    await session.commit()
    return _to_out(row, job)


@router.get("/{application_id}", response_model=ApplicationOut)
async def get_application(application_id: uuid.UUID, session: Session,
                          user: CurrentUser):
    row = await _owned(session, user, application_id)
    job = await session.get(Job, row.job_id)
    return _to_out(row, job)


@router.patch("/{application_id}", response_model=ApplicationOut)
async def update_application(application_id: uuid.UUID,
                             body: UpdateApplicationIn, session: Session,
                             user: CurrentUser):
    row = await _owned(session, user, application_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    row.updated_at = datetime.now(UTC)
    await session.commit()
    job = await session.get(Job, row.job_id)
    return _to_out(row, job)


@router.delete("/{application_id}", status_code=204)
async def delete_application(application_id: uuid.UUID, session: Session,
                             user: CurrentUser) -> Response:
    row = await _owned(session, user, application_id)
    row.deleted_at = datetime.now(UTC)
    await session.commit()
    return Response(status_code=204)


@router.post("/{application_id}/status", response_model=ApplicationOut)
async def change_status(application_id: uuid.UUID, body: ChangeStatusIn,
                        session: Session, user: CurrentUser):
    row = await _owned(session, user, application_id)
    if body.to_status != row.status:
        session.add(ApplicationEvent(application_id=row.id,
                                     from_status=row.status,
                                     to_status=body.to_status, note=body.note))
        row.status = body.to_status
        if body.to_status == "APPLIED" and row.applied_at is None:
            row.applied_at = datetime.now(UTC)
        row.updated_at = datetime.now(UTC)
        await audit(session, "tracker.status_changed", user_id=user.id,
                    entity_type="application", entity_id=str(row.id),
                    detail={"to": body.to_status})
    await session.commit()
    job = await session.get(Job, row.job_id)
    return _to_out(row, job)


@router.get("/{application_id}/events",
            response_model=list[ApplicationEventOut])
async def list_events(application_id: uuid.UUID, session: Session,
                      user: CurrentUser):
    await _owned(session, user, application_id)
    return (await session.scalars(
        select(ApplicationEvent)
        .where(ApplicationEvent.application_id == application_id)
        .order_by(ApplicationEvent.created_at))).all()
