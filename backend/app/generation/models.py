"""GeneratedDocument ORM (schema owned by Alembic 0001)."""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base

document_type = ENUM("TAILORED_RESUME", "COVER_LETTER", "RECRUITER_EMAIL",
                     "LINKEDIN_MESSAGE", "COLD_EMAIL",
                     name="document_type", create_type=False)


class GeneratedDocument(Base):
    __tablename__ = "generated_documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"))
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"))
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("applications.id", ondelete="SET NULL"))
    doc_type: Mapped[str] = mapped_column(document_type)
    content_md: Mapped[str | None] = mapped_column(Text)
    file_path: Mapped[str | None] = mapped_column(Text)
    source_resume: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("resumes.id", ondelete="SET NULL"))
    prompt_key: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[int | None] = mapped_column(Integer)
    model: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())
