"""MatchScore ORM (schema owned by Alembic 0001)."""
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base


class MatchScore(Base):
    __tablename__ = "match_scores"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"))
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"))
    resume_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("resumes.id", ondelete="CASCADE"))
    overall: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    ats_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    resume_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    salary_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    location_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    visa_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    skill_gap: Mapped[list] = mapped_column(JSONB, default=list)
    reasoning: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())

    __table_args__ = (UniqueConstraint("user_id", "job_id", "resume_id",
                                       name="match_scores_user_id_job_id_resume_id_key"),)
