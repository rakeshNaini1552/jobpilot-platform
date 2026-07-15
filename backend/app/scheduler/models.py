"""Scheduler ORM (schema owned by Alembic 0001)."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import ENUM, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base

run_status = ENUM("RUNNING", "SUCCESS", "FAILED", "PARTIAL",
                  name="run_status", create_type=False)


class ScheduledTask(Base):
    __tablename__ = "scheduled_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(Text, unique=True)
    cron: Mapped[str] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(Text, default="America/Chicago")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())


class ScheduledRun(Base):
    __tablename__ = "scheduled_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_key: Mapped[str] = mapped_column(
        ForeignKey("scheduled_tasks.key", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(run_status, default="RUNNING")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stats: Mapped[dict] = mapped_column(JSONB, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
