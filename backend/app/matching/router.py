"""Matches endpoints — ranked list and per-job breakdown."""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.api import CurrentUser
from app.common.pagination import Page, PageParams, page_params
from app.connector.models import Job
from app.connector.schemas import JobOut
from app.core.db import get_session
from app.core.errors import Problem

from .models import MatchScore
from .schemas import MatchOut, MatchPage, MatchScoreOut

router = APIRouter(prefix="/matches", tags=["matches"])
job_match_router = APIRouter(prefix="/jobs", tags=["matches"])

Session = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=MatchPage)
async def list_matches(
    session: Session, user: CurrentUser,
    params: Annotated[PageParams, Depends(page_params)],
    min_score: float = 0,
):
    base = (select(MatchScore, Job).join(Job, MatchScore.job_id == Job.id)
            .where(MatchScore.user_id == user.id,
                   MatchScore.overall >= min_score,
                   Job.status == "ACTIVE"))
    total = await session.scalar(select(func.count()).select_from(base.subquery()))
    rows = (await session.execute(
        base.order_by(MatchScore.overall.desc())
        .offset((params.page - 1) * params.size).limit(params.size))).all()
    items = [MatchOut(job=JobOut.model_validate(job),
                      score=MatchScoreOut.model_validate(ms))
             for ms, job in rows]
    return Page.of(items, params, total or 0)


@job_match_router.get("/{job_id}/match", response_model=MatchScoreOut)
async def get_match(job_id: uuid.UUID, session: Session, user: CurrentUser):
    ms = await session.scalar(
        select(MatchScore).where(MatchScore.user_id == user.id,
                                 MatchScore.job_id == job_id)
        .order_by(MatchScore.created_at.desc()))
    if ms is None:
        raise Problem(404, "No match score for this job yet",
                      type_suffix="not-found")
    return ms
