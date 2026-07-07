"""Match scoring persistence: score jobs for a user against their default
resume + preferences, upserting match_scores. Sync (worker) flavor — called
from ingestion tasks; the API reads what workers wrote."""
from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.ai.extraction import Extraction
from app.connector.models import Job, JobExtraction
from app.resume.models import Resume
from app.user.models import Preferences

from .engine import MatchInput, score
from .models import MatchScore

log = structlog.get_logger("matching")


def _build_input(job: Job, extraction: JobExtraction | None,
                 resume: Resume, prefs: Preferences | None) -> MatchInput:
    ext = Extraction(
        skills=list(extraction.skills) if extraction else [],
        sponsorship=extraction.sponsorship if extraction else "UNKNOWN")
    return MatchInput(
        job_title=job.title,
        job_workplace=job.workplace,
        job_salary_min=job.salary_min, job_salary_max=job.salary_max,
        extraction=ext,
        resume_skills=(resume.structured or {}).get("skills", []),
        resume_text=resume.raw_text or "",
        pref_salary_min=prefs.salary_min if prefs else None,
        pref_workplace=list(prefs.workplace_types) if prefs else [],
        needs_sponsorship=bool(prefs.needs_sponsorship) if prefs else False)


def score_jobs_for_user(session: Session, user_id: uuid.UUID,
                        job_ids: list[uuid.UUID] | None = None,
                        limit: int = 200) -> int:
    """Score the given jobs (or recent unscored ones) for the user.
    No default resume ⇒ nothing to score against; returns 0."""
    resume = session.scalar(select(Resume).where(
        Resume.user_id == user_id, Resume.is_default.is_(True)))
    if resume is None:
        log.info("scoring_skipped_no_resume", user_id=str(user_id))
        return 0
    prefs = session.get(Preferences, user_id)

    stmt = select(Job, JobExtraction).outerjoin(
        JobExtraction, JobExtraction.job_id == Job.id
    ).where(Job.status == "ACTIVE")
    if job_ids is not None:
        if not job_ids:
            return 0
        stmt = stmt.where(Job.id.in_(job_ids))
    rows = session.execute(stmt.limit(limit)).all()

    scored = 0
    for job, extraction in rows:
        result = score(_build_input(job, extraction, resume, prefs))
        values = {
            "user_id": user_id, "job_id": job.id, "resume_id": resume.id,
            "overall": result.overall, "ats_pct": result.ats_pct,
            "resume_pct": result.resume_pct, "salary_score": result.salary_score,
            "location_score": result.location_score, "visa_score": result.visa_score,
            "skill_gap": result.skill_gap,
        }
        session.execute(
            pg_insert(MatchScore).values(**values)
            .on_conflict_do_update(
                index_elements=["user_id", "job_id", "resume_id"],
                set_={k: v for k, v in values.items()
                      if k not in ("user_id", "job_id", "resume_id")}))
        scored += 1
    log.info("scoring_complete", user_id=str(user_id), scored=scored)
    return scored
