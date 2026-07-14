"""Analytics DTOs — typed contract for the dashboard and trends payloads."""
from pydantic import BaseModel


class WeekCount(BaseModel):
    week: str
    count: int


class CompanyCount(BaseModel):
    company: str
    count: int


class BucketCount(BaseModel):
    bucket: str
    count: int


class FunnelEntry(BaseModel):
    status: str
    count: int


class TopMatch(BaseModel):
    title: str
    url: str
    score: float


class DashboardOut(BaseModel):
    jobs_found: int
    jobs_applied: int
    interviews: int
    rejections: int
    offers: int
    success_rate: float
    recruiter_response_rate: float
    applications_by_week: list[WeekCount]
    applications_by_company: list[CompanyCount]
    match_score_distribution: list[BucketCount]
    salary_distribution: list[BucketCount]
    funnel: list[FunnelEntry]
    ai_suggestions: list[str]
    top_matches: list[TopMatch]


class DayCount(BaseModel):
    date: str
    count: int


class BoomingCompany(BaseModel):
    company: str
    recent: int
    previous: int
    growth_pct: float


class TechDemand(BaseModel):
    skill: str
    count: int


class TrendsOut(BaseModel):
    postings_per_day: list[DayCount]
    booming_companies: list[BoomingCompany]
    tech_demand: list[TechDemand]
