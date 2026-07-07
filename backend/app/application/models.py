"""Application tracker ORM (schema owned by Alembic 0001).

Full CRUD/status-transition logic lands in Phase 9; the model is defined
here so matching, analytics, and the assistant can read the pipeline now."""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base

application_status = ENUM(
    "SAVED", "INTERESTED", "RESUME_GENERATED", "APPLIED", "RECRUITER_CONTACTED",
    "OA_RECEIVED", "INTERVIEW_SCHEDULED", "REJECTED", "OFFER", "ACCEPTED",
    "DECLINED", name="application_status", create_type=False)
apply_method = ENUM("MANUAL", "API", "AUTOMATED_FORM", "EMAIL", "REFERRAL",
                    name="apply_method", create_type=False)


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"))
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"))
    resume_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("resumes.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(application_status, default="SAVED")
    method: Mapped[str | None] = mapped_column(apply_method)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    salary_offered: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())

    __table_args__ = (UniqueConstraint("user_id", "job_id",
                                       name="applications_user_id_job_id_key"),)


actor_type = ENUM("USER", "SYSTEM", "ASSISTANT", name="actor_type",
                  create_type=False)


class ApplicationEvent(Base):
    __tablename__ = "application_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"))
    from_status: Mapped[str | None] = mapped_column(application_status)
    to_status: Mapped[str] = mapped_column(application_status)
    actor: Mapped[str] = mapped_column(actor_type, default="USER")
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())
