"""Resume DTOs — mirror api/openapi.yaml (tag: resumes)."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ResumeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    is_default: bool
    mime_type: str | None = None
    structured: dict | None = None
    created_at: datetime
    updated_at: datetime


class ResumeAnalysis(BaseModel):
    ats_score: float
    strengths: list[str] = []
    gaps: list[str] = []
    suggestions: list[str] = []
    keyword_coverage: dict[str, bool] = {}
