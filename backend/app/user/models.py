"""ORM models over the identity/profile tables (schema owned by Alembic 0001)."""
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, ENUM, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base

user_role = ENUM("USER", "ADMIN", name="user_role", create_type=False)
employment_type = ENUM("FULL_TIME", "PART_TIME", "CONTRACT", "INTERNSHIP",
                       "TEMPORARY", "UNKNOWN", name="employment_type", create_type=False)
contract_arrangement = ENUM("W2", "C1099", "C2C", "UNSPECIFIED",
                            name="contract_arrangement", create_type=False)
workplace_type = ENUM("REMOTE", "HYBRID", "ONSITE", "UNKNOWN",
                      name="workplace_type", create_type=False)
seniority_level = ENUM("ENTRY", "MID", "SENIOR", "LEAD", "PRINCIPAL", "UNKNOWN",
                       name="seniority_level", create_type=False)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(Text, unique=True)
    password_hash: Mapped[str | None] = mapped_column(Text)
    full_name: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(user_role, default="USER")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    timezone: Mapped[str] = mapped_column(Text, default="America/Chicago")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())


class OAuthAccount(Base):
    __tablename__ = "oauth_accounts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(Text)
    provider_user_id: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())


class Preferences(Base):
    __tablename__ = "preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    desired_titles: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    employment_types: Mapped[list[str]] = mapped_column(
        ARRAY(employment_type), default=lambda: ["FULL_TIME"])
    contract_arrangements: Mapped[list[str]] = mapped_column(
        ARRAY(contract_arrangement), default=list)
    workplace_types: Mapped[list[str]] = mapped_column(
        ARRAY(workplace_type), default=list)
    locations: Mapped[list] = mapped_column(JSONB, default=list)
    countries: Mapped[list[str]] = mapped_column(ARRAY(Text), default=lambda: ["US"])
    seniority: Mapped[str | None] = mapped_column(seniority_level)
    years_experience: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    visa_status: Mapped[str | None] = mapped_column(Text)
    work_authorization: Mapped[str | None] = mapped_column(Text)
    needs_sponsorship: Mapped[bool] = mapped_column(Boolean, default=False)
    open_to_staffing: Mapped[bool] = mapped_column(Boolean, default=True)
    salary_min: Mapped[int | None] = mapped_column(Integer)
    salary_max: Mapped[int | None] = mapped_column(Integer)
    salary_currency: Mapped[str] = mapped_column(String(3), default="USD")
    availability_date: Mapped[date | None] = mapped_column(Date)
    notice_period_days: Mapped[int | None] = mapped_column(Integer)
    auto_apply_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_apply_min_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=70)
    auto_apply_daily_cap: Mapped[int] = mapped_column(Integer, default=25)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())
