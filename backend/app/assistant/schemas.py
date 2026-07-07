"""Assistant DTOs — mirror api/openapi.yaml (tag: assistant)."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str | None = None
    created_at: datetime
    updated_at: datetime


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    role: str
    content: str
    created_at: datetime


class ConversationDetail(ConversationOut):
    messages: list[MessageOut] = []


class CreateConversationIn(BaseModel):
    title: str | None = None


class SendMessageIn(BaseModel):
    content: str


class AssistantReplyOut(BaseModel):
    content: str
    action: str | None = None
    model: str | None = None
