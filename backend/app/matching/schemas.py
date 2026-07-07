"""Match DTOs — mirror api/openapi.yaml (tag: matches)."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.connector.schemas import JobOut


class MatchScoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    job_id: uuid.UUID
    resume_id: uuid.UUID
    overall: float
    ats_pct: float | None = None
    resume_pct: float | None = None
    salary_score: float | None = None
    location_score: float | None = None
    visa_score: float | None = None
    skill_gap: list = []
    reasoning: str | None = None
    created_at: datetime


class MatchOut(BaseModel):
    job: JobOut
    score: MatchScoreOut


class MatchPage(BaseModel):
    items: list[MatchOut]
    page: int
    size: int
    total: int
