"""Profile DTOs — mirror api/openapi.yaml (tag: profile)."""
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EmploymentType = Literal["FULL_TIME", "PART_TIME", "CONTRACT", "INTERNSHIP",
                         "TEMPORARY", "UNKNOWN"]
ContractArrangement = Literal["W2", "C1099", "C2C", "UNSPECIFIED"]
WorkplaceType = Literal["REMOTE", "HYBRID", "ONSITE", "UNKNOWN"]
SeniorityLevel = Literal["ENTRY", "MID", "SENIOR", "LEAD", "PRINCIPAL", "UNKNOWN"]


class UserPatch(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    timezone: str | None = None


class LocationPref(BaseModel):
    city: str | None = None
    state: str | None = None
    country: str | None = None
    radius_mi: int | None = None


class PreferencesIO(BaseModel):
    """Single schema for GET response and PUT request (full replace)."""
    model_config = ConfigDict(from_attributes=True)

    desired_titles: list[str] = []
    employment_types: list[EmploymentType] = ["FULL_TIME"]
    contract_arrangements: list[ContractArrangement] = []
    workplace_types: list[WorkplaceType] = []
    locations: list[LocationPref] = []
    countries: list[str] = ["US"]
    seniority: SeniorityLevel | None = None
    years_experience: Decimal | None = None
    visa_status: str | None = None
    work_authorization: str | None = None
    needs_sponsorship: bool = False
    open_to_staffing: bool = True
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str = "USD"
    availability_date: date | None = None
    notice_period_days: int | None = None
    auto_apply_enabled: bool = False
    auto_apply_min_score: Decimal = Decimal(70)
    auto_apply_daily_cap: int = Field(default=25, ge=0, le=200)
