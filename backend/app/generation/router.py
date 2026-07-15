"""Documents endpoints — generate/list/get tailored application materials.

Generation runs inline (a few seconds worst-case with a slow LLM, instant on
the template fallback) and every draft passes the truthfulness guardrail
before it is stored, so a stored document is always safe to send."""
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.api import CurrentUser
from app.common.audit import audit
from app.connector.models import Company, Job
from app.core.db import get_session
from app.core.errors import Problem
from app.resume.models import Resume

from .documents import generate
from .models import GeneratedDocument

router = APIRouter(prefix="/documents", tags=["documents"])

Session = Annotated[AsyncSession, Depends(get_session)]

DocType = Literal["TAILORED_RESUME", "COVER_LETTER", "RECRUITER_EMAIL",
                  "LINKEDIN_MESSAGE", "COLD_EMAIL"]


class GenerateIn(BaseModel):
    job_id: uuid.UUID
    doc_type: DocType
    resume_id: uuid.UUID | None = None      # defaults to the default resume


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    job_id: uuid.UUID | None = None
    doc_type: str
    content_md: str | None = None
    model: str | None = None
    created_at: object


@router.post("", response_model=DocumentOut, status_code=201)
async def generate_document(body: GenerateIn, session: Session, user: CurrentUser):
    job = await session.get(Job, body.job_id)
    if job is None or job.status != "ACTIVE":
        raise Problem(404, "Job not found", type_suffix="not-found")

    if body.resume_id:
        resume = await session.get(Resume, body.resume_id)
        if resume is None or resume.user_id != user.id:
            raise Problem(404, "Resume not found", type_suffix="not-found")
    else:
        resume = await session.scalar(
            select(Resume).where(Resume.user_id == user.id,
                                 Resume.is_default.is_(True)))
        if resume is None:
            raise Problem(409, "No resume on file",
                          "Upload a resume before generating documents.",
                          type_suffix="no-resume")

    company = await session.get(Company, job.company_id) if job.company_id else None
    resume_text = resume.raw_text or ""
    resume_skills = (resume.structured or {}).get("skills", [])
    jd = f"{job.title}\n{job.description_md or ''}"
    overlap = [s for s in resume_skills if s.lower() in jd.lower()]

    doc = generate(
        body.doc_type,
        candidate_name=user.full_name,
        resume_text=resume_text,
        overlap_skills=overlap or resume_skills[:5],
        job_title=job.title,
        job_company=company.name if company else "the company",
        job_description=job.description_md or "")

    row = GeneratedDocument(
        user_id=user.id, job_id=job.id, doc_type=body.doc_type,
        content_md=doc.content, source_resume=resume.id, model=doc.model)
    session.add(row)
    await audit(session, "generation.document_created", user_id=user.id,
                entity_type="job", entity_id=str(job.id),
                detail={"doc_type": body.doc_type,
                        "guardrail_ok": doc.guardrail.ok,
                        "model": doc.model})
    await session.commit()
    await session.refresh(row)
    return row


@router.get("", response_model=list[DocumentOut])
async def list_documents(session: Session, user: CurrentUser,
                         job_id: uuid.UUID | None = None):
    stmt = (select(GeneratedDocument)
            .where(GeneratedDocument.user_id == user.id)
            .order_by(GeneratedDocument.created_at.desc()).limit(100))
    if job_id:
        stmt = stmt.where(GeneratedDocument.job_id == job_id)
    return (await session.scalars(stmt)).all()


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(document_id: uuid.UUID, session: Session,
                       user: CurrentUser):
    row = await session.get(GeneratedDocument, document_id)
    if row is None or row.user_id != user.id:
        raise Problem(404, "Document not found", type_suffix="not-found")
    return row
