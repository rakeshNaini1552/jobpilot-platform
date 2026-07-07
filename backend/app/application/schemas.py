"""Tracker DTOs — mirror api/openapi.yaml (tag: applications)."""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.connector.schemas import JobOut

ApplicationStatus = Literal[
    "SAVED", "INTERESTED", "RESUME_GENERATED", "APPLIED", "RECRUITER_CONTACTED",
    "OA_RECEIVED", "INTERVIEW_SCHEDULED", "REJECTED", "OFFER", "ACCEPTED",
    "DECLINED"]


class ApplicationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    job: JobOut
    status: str
    method: str | None = None
    applied_at: datetime | None = None
    deadline_at: datetime | None = None
    next_action_at: datetime | None = None
    salary_offered: int | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class ApplicationPage(BaseModel):
    items: list[ApplicationOut]
    page: int
    size: int
    total: int


class CreateApplicationIn(BaseModel):
    job_id: uuid.UUID
    status: ApplicationStatus = "SAVED"
    notes: str | None = None


class UpdateApplicationIn(BaseModel):
    notes: str | None = None
    salary_offered: int | None = None
    deadline_at: datetime | None = None
    next_action_at: datetime | None = None
    resume_id: uuid.UUID | None = None


class ChangeStatusIn(BaseModel):
    to_status: ApplicationStatus
    note: str | None = None


class ApplicationEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    from_status: str | None = None
    to_status: str
    actor: str
    note: str | None = None
    created_at: datetime
