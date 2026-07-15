"""Notification ORM (schema owned by Alembic 0001)."""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, SmallInteger, Text
from sqlalchemy.dialects.postgresql import ENUM, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base

notification_channel = ENUM("EMAIL", "SLACK", "DISCORD",
                            name="notification_channel", create_type=False)
delivery_status = ENUM("PENDING", "SENT", "FAILED", "SKIPPED",
                       name="delivery_status", create_type=False)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"))
    channel: Mapped[str] = mapped_column(notification_channel)
    template: Mapped[str] = mapped_column(Text)
    subject: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(delivery_status, default="PENDING")
    error: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())


class NotificationSettings(Base):
    __tablename__ = "notification_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    email_enabled: Mapped[bool] = mapped_column(default=True)
    daily_report_hour: Mapped[int] = mapped_column(SmallInteger, default=21)
    slack_webhook_enc: Mapped[str | None] = mapped_column(Text)
    discord_webhook_enc: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())
