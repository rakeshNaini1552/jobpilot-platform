"""Resume endpoints: upload (docx/pdf/txt), list, default, analysis."""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, UploadFile
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from app.auth.api import CurrentUser
from app.core.db import get_session
from app.core.errors import Problem

from .models import Resume
from .parser import detect_skills, parse_file
from .schemas import ResumeAnalysis, ResumeOut

router = APIRouter(prefix="/resumes", tags=["resumes"])

Session = Annotated[AsyncSession, Depends(get_session)]


async def _owned(session, user, resume_id) -> Resume:
    resume = await session.get(Resume, resume_id)
    if resume is None or resume.user_id != user.id:
        raise Problem(404, "Resume not found", type_suffix="not-found")
    return resume


@router.get("", response_model=list[ResumeOut])
async def list_resumes(session: Session, user: CurrentUser):
    return (await session.scalars(
        select(Resume).where(Resume.user_id == user.id)
        .order_by(Resume.is_default.desc(), Resume.created_at.desc()))).all()


@router.post("", response_model=ResumeOut, status_code=201)
async def upload_resume(name: str, file: UploadFile, session: Session,
                        user: CurrentUser):
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise Problem(422, "Resume file too large (max 5 MB)", type_suffix="too-large")
    raw_text = parse_file(file.filename or "", content, file.content_type or "")
    if not raw_text.strip():
        raise Problem(422, "No text could be extracted from the file",
                      type_suffix="resume-empty")

    has_default = await session.scalar(
        select(Resume.id).where(Resume.user_id == user.id,
                                Resume.is_default.is_(True)))
    resume = Resume(user_id=user.id, name=name, mime_type=file.content_type,
                    raw_text=raw_text, is_default=has_default is None,
                    structured={"skills": detect_skills(raw_text)})
    session.add(resume)
    await session.commit()
    await session.refresh(resume)
    return resume


@router.get("/{resume_id}", response_model=ResumeOut)
async def get_resume(resume_id: uuid.UUID, session: Session, user: CurrentUser):
    return await _owned(session, user, resume_id)


@router.delete("/{resume_id}", status_code=204)
async def delete_resume(resume_id: uuid.UUID, session: Session,
                        user: CurrentUser) -> Response:
    resume = await _owned(session, user, resume_id)
    await session.delete(resume)
    await session.commit()
    return Response(status_code=204)


@router.post("/{resume_id}/default", status_code=204)
async def set_default(resume_id: uuid.UUID, session: Session,
                      user: CurrentUser) -> Response:
    resume = await _owned(session, user, resume_id)
    await session.execute(update(Resume).where(Resume.user_id == user.id)
                          .values(is_default=False))
    resume.is_default = True
    await session.commit()
    return Response(status_code=204)


@router.get("/{resume_id}/analysis", response_model=ResumeAnalysis)
async def analyze_resume(resume_id: uuid.UUID, session: Session,
                         user: CurrentUser):
    """Deterministic ATS checks; AI suggestions layered on when available."""
    resume = await _owned(session, user, resume_id)
    text = resume.raw_text or ""
    skills = (resume.structured or {}).get("skills", [])
    checks = {
        "has_email": "@" in text,
        "has_phone": any(c.isdigit() for c in text) and
                     sum(c.isdigit() for c in text) >= 10,
        "has_skills_section": "skill" in text.lower(),
        "has_experience_section": "experience" in text.lower(),
        "reasonable_length": 1200 <= len(text) <= 12000,
        "skills_detected": len(skills) >= 5,
    }
    ats_score = round(100 * sum(checks.values()) / len(checks), 1)
    suggestions = [msg for ok, msg in [
        (checks["has_email"], "Add a contact email."),
        (checks["has_phone"], "Add a phone number."),
        (checks["has_skills_section"], "Add an explicit Skills section."),
        (checks["has_experience_section"], "Add an Experience section."),
        (checks["reasonable_length"], "Aim for 1-2 pages of substantive content."),
        (checks["skills_detected"], "List more concrete technologies."),
    ] if not ok]
    return ResumeAnalysis(ats_score=ats_score, strengths=skills[:10],
                          gaps=[], suggestions=suggestions,
                          keyword_coverage=checks)
