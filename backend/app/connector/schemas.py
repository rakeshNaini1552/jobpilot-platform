"""Jobs DTOs — mirror api/openapi.yaml (tags: jobs)."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    website: str | None = None
    is_staffing_firm: bool = False
    ats_type: str | None = None


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str
    connector_id: str
    url: str
    location_text: str | None = None
    workplace: str
    employment: str
    arrangement: str
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    posted_at: datetime | None = None


class JobPage(BaseModel):
    items: list[JobOut]
    page: int
    size: int
    total: int


class SearchRunOut(BaseModel):
    id: str
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    stats: dict = {}
