"""Jobs endpoints — browse discovered jobs, trigger/poll search runs, export."""
import csv
import io
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from app.auth.api import CurrentUser
from app.common.pagination import Page, PageParams, page_params
from app.core.db import get_session
from app.core.errors import Problem

from .models import Job
from .schemas import JobOut, JobPage, SearchRunOut

router = APIRouter(prefix="/jobs", tags=["jobs"])
runs_router = APIRouter(prefix="/search-runs", tags=["jobs"])

Session = Annotated[AsyncSession, Depends(get_session)]


def _apply_filters(stmt, *, q, employment, arrangement, workplace, country,
                   sponsorship, min_salary, posted_within_hours):
    if q:
        stmt = stmt.where(Job.title.ilike(f"%{q}%"))
    if employment:
        stmt = stmt.where(Job.employment == employment)
    if arrangement:
        stmt = stmt.where(Job.arrangement == arrangement)
    if workplace:
        stmt = stmt.where(Job.workplace == workplace)
    if country:
        stmt = stmt.where(Job.country == country.upper())
    if min_salary:
        stmt = stmt.where(Job.salary_max >= min_salary)
    if posted_within_hours:
        cutoff = datetime.now(UTC) - timedelta(hours=posted_within_hours)
        stmt = stmt.where(Job.posted_at >= cutoff)
    return stmt


@router.get("", response_model=JobPage)
async def list_jobs(
    session: Session, user: CurrentUser,
    params: Annotated[PageParams, Depends(page_params)],
    q: str | None = None,
    employment: str | None = None,
    arrangement: str | None = None,
    workplace: str | None = None,
    country: str | None = None,
    sponsorship: str | None = None,
    min_salary: int | None = None,
    posted_within_hours: int = Query(default=168),
    sort: str = Query(default="-posted_at"),
):
    base = _apply_filters(
        select(Job).where(Job.status == "ACTIVE"),
        q=q, employment=employment, arrangement=arrangement, workplace=workplace,
        country=country, sponsorship=sponsorship, min_salary=min_salary,
        posted_within_hours=posted_within_hours)

    total = await session.scalar(select(func.count()).select_from(base.subquery()))
    order = Job.posted_at.desc() if sort.startswith("-") else Job.posted_at.asc()
    rows = (await session.scalars(
        base.order_by(order.nullslast())
        .offset((params.page - 1) * params.size).limit(params.size))).all()
    return Page.of([JobOut.model_validate(r) for r in rows], params, total or 0)


@router.get("/export")
async def export_jobs(session: Session, user: CurrentUser,
                      posted_within_hours: int = 48):
    cutoff = datetime.now(UTC) - timedelta(hours=posted_within_hours)
    rows = (await session.scalars(
        select(Job).where(Job.status == "ACTIVE", Job.posted_at >= cutoff)
        .order_by(Job.posted_at.desc().nullslast()).limit(1000))).all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["title", "company_url", "connector", "location",
                     "employment", "arrangement", "url"])
    for r in rows:
        writer.writerow([r.title, r.url, r.connector_id, r.location_text or "",
                         r.employment, r.arrangement, r.url])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=jobpilot_jobs.csv"})


@runs_router.post("", response_model=SearchRunOut, status_code=202)
async def trigger_search_run(user: CurrentUser):
    from app.ingestion.tasks import run_ingestion_for_user
    try:
        async_result = run_ingestion_for_user.delay(str(user.id))
        run_id = async_result.id
    except Exception:
        # No broker in dev/test — surface a clear, non-500 problem.
        raise Problem(503, "Task queue unavailable",
                      "Start the Celery worker/Redis to run ingestion.",
                      type_suffix="queue-unavailable") from None
    return SearchRunOut(id=run_id, status="RUNNING")


@runs_router.get("/{run_id}", response_model=SearchRunOut)
async def get_search_run(run_id: str, user: CurrentUser):
    from celery.result import AsyncResult
    res = AsyncResult(run_id)
    status_map = {"PENDING": "RUNNING", "STARTED": "RUNNING",
                  "SUCCESS": "SUCCESS", "FAILURE": "FAILED"}
    return SearchRunOut(id=run_id, status=status_map.get(res.status, "RUNNING"),
                        stats=res.result if isinstance(res.result, dict) else {})
