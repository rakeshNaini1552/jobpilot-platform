"""ORM for connector settings, companies, jobs, extractions, watchlist
(schema owned by Alembic 0001)."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, ENUM, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base

compliance_mode = ENUM("OFFICIAL_API", "PUBLIC_FEED", "SEARCH_LINK",
                       "USER_AUTHORIZED_AUTOMATION", name="compliance_mode",
                       create_type=False)
employment_type = ENUM("FULL_TIME", "PART_TIME", "CONTRACT", "INTERNSHIP",
                       "TEMPORARY", "UNKNOWN", name="employment_type", create_type=False)
contract_arrangement = ENUM("W2", "C1099", "C2C", "UNSPECIFIED",
                            name="contract_arrangement", create_type=False)
workplace_type = ENUM("REMOTE", "HYBRID", "ONSITE", "UNKNOWN",
                      name="workplace_type", create_type=False)
sponsorship_flag = ENUM("SPONSOR_FRIENDLY", "NO_SPONSOR", "UNKNOWN",
                        name="sponsorship_flag", create_type=False)
seniority_level = ENUM("ENTRY", "MID", "SENIOR", "LEAD", "PRINCIPAL", "UNKNOWN",
                       name="seniority_level", create_type=False)
job_status = ENUM("ACTIVE", "CLOSED", "EXPIRED", "DUPLICATE",
                  name="job_status", create_type=False)
extraction_method = ENUM("LLM", "HEURISTIC", "MIXED",
                         name="extraction_method", create_type=False)


class ConnectorSetting(Base):
    __tablename__ = "connector_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connector_id: Mapped[str] = mapped_column(Text, unique=True)
    display_name: Mapped[str] = mapped_column(Text)
    compliance_mode: Mapped[str] = mapped_column(compliance_mode)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    rate_limit_per_min: Mapped[int] = mapped_column(Integer, default=30)
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text)
    normalized_name: Mapped[str] = mapped_column(Text, unique=True)
    website: Mapped[str | None] = mapped_column(Text)
    industry: Mapped[str | None] = mapped_column(Text)
    size_range: Mapped[str | None] = mapped_column(Text)
    is_staffing_firm: Mapped[bool] = mapped_column(Boolean, default=False)
    ats_type: Mapped[str | None] = mapped_column(Text)
    careers_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    connector_id: Mapped[str] = mapped_column(Text)
    external_id: Mapped[str | None] = mapped_column(Text)
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(Text)
    description_md: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    dedupe_hash: Mapped[str] = mapped_column(Text, unique=True)
    location_text: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(String(2))
    workplace: Mapped[str] = mapped_column(workplace_type, default="UNKNOWN")
    employment: Mapped[str] = mapped_column(employment_type, default="UNKNOWN")
    arrangement: Mapped[str] = mapped_column(contract_arrangement, default="UNSPECIFIED")
    salary_min: Mapped[int | None] = mapped_column(Integer)
    salary_max: Mapped[int | None] = mapped_column(Integer)
    salary_currency: Mapped[str | None] = mapped_column(String(3))
    salary_period: Mapped[str | None] = mapped_column(Text)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                    server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                   server_default=func.now())
    status: Mapped[str] = mapped_column(job_status, default="ACTIVE")
    raw: Mapped[dict] = mapped_column(JSONB, default=dict)

    __table_args__ = (UniqueConstraint("connector_id", "external_id",
                                       name="jobs_connector_id_external_id_key"),)


class JobExtraction(Base):
    __tablename__ = "job_extractions"

    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True)
    skills: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    tech_stack: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    responsibilities: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    benefits: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    sponsorship: Mapped[str] = mapped_column(sponsorship_flag, default="UNKNOWN")
    seniority: Mapped[str] = mapped_column(seniority_level, default="UNKNOWN")
    recruiter_name: Mapped[str | None] = mapped_column(Text)
    recruiter_contact: Mapped[str | None] = mapped_column(Text)
    method: Mapped[str] = mapped_column(extraction_method)
    model: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())


class CompanyWatchlist(Base):
    __tablename__ = "company_watchlist"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"))
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"))
    connector_id: Mapped[str] = mapped_column(
        ForeignKey("connector_settings.connector_id"))
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())
