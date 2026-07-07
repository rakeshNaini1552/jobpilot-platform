"""Assistant endpoints — conversations and messages (Jarvis)."""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from app.auth.api import CurrentUser
from app.core.db import get_session
from app.core.errors import Problem

from . import service
from .models import AiConversation, AiMessage
from .schemas import (
    AssistantReplyOut,
    ConversationDetail,
    ConversationOut,
    CreateConversationIn,
    MessageOut,
    SendMessageIn,
)

router = APIRouter(prefix="/assistant", tags=["assistant"])

Session = Annotated[AsyncSession, Depends(get_session)]


async def _owned_conversation(session, user, conversation_id) -> AiConversation:
    conv = await session.get(AiConversation, conversation_id)
    if conv is None or conv.user_id != user.id:
        raise Problem(404, "Conversation not found", type_suffix="not-found")
    return conv


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(session: Session, user: CurrentUser):
    rows = (await session.scalars(
        select(AiConversation).where(AiConversation.user_id == user.id)
        .order_by(AiConversation.updated_at.desc()))).all()
    return rows


@router.post("/conversations", response_model=ConversationOut, status_code=201)
async def create_conversation(body: CreateConversationIn, session: Session,
                              user: CurrentUser):
    conv = await service.create_conversation(session, user.id, body.title)
    await session.commit()
    return conv


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(conversation_id: uuid.UUID, session: Session,
                           user: CurrentUser):
    conv = await _owned_conversation(session, user, conversation_id)
    messages = (await session.scalars(
        select(AiMessage).where(AiMessage.conversation_id == conv.id)
        .order_by(AiMessage.created_at))).all()
    detail = ConversationDetail.model_validate(conv)
    detail.messages = [MessageOut.model_validate(m) for m in messages]
    return detail


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: uuid.UUID, session: Session,
                              user: CurrentUser) -> Response:
    conv = await _owned_conversation(session, user, conversation_id)
    await session.delete(conv)
    await session.commit()
    return Response(status_code=204)


@router.post("/conversations/{conversation_id}/messages",
             response_model=AssistantReplyOut)
async def send_message(conversation_id: uuid.UUID, body: SendMessageIn,
                       session: Session, user: CurrentUser):
    conv = await _owned_conversation(session, user, conversation_id)
    reply = await service.ask(session, user.id, conv.id, body.content)
    await session.commit()
    return AssistantReplyOut(content=reply.content, action=reply.action,
                             model=reply.model)
