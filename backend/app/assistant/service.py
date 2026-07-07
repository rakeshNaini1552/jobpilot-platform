"""Assistant ("Jarvis") — answers questions grounded in the user's own data.

Retrieval is SQL over the user's jobs / matches / applications (RAG over
pgvector is added when embeddings are configured; this works with zero AI).
Intent detection is rule-based so actions fire reliably; the natural-language
answer uses the AI gateway when available and a deterministic responder
otherwise. Every turn is persisted to ai_conversations / ai_messages.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.models import Application
from app.connector.models import Job
from app.matching.models import MatchScore

from .models import AiConversation, AiMessage


@dataclass
class AssistantReply:
    content: str
    action: str | None            # scrape | tailor | None — a hint for the UI
    model: str | None


_INTENT_ACTION = [
    (re.compile(r"\b(scrape|search|find new|hunt).{0,20}job", re.I), "scrape"),
    (re.compile(r"\b(tailor|customize|rewrite).{0,15}resume", re.I), "tailor"),
]


async def _context(session: AsyncSession, user_id: uuid.UUID) -> dict:
    total_jobs = await session.scalar(
        select(func.count()).select_from(Job).where(Job.status == "ACTIVE")) or 0
    top = (await session.execute(
        select(Job.title, Job.url, MatchScore.overall)
        .join(MatchScore, MatchScore.job_id == Job.id)
        .where(MatchScore.user_id == user_id)
        .order_by(MatchScore.overall.desc()).limit(5))).all()
    status_rows = (await session.execute(
        select(Application.status, func.count())
        .where(Application.user_id == user_id, Application.deleted_at.is_(None))
        .group_by(Application.status))).all()
    return {
        "total_jobs": total_jobs,
        "top_matches": [{"title": t, "url": u, "score": float(s)} for t, u, s in top],
        "pipeline": {status: n for status, n in status_rows},
    }


def _render_context(ctx: dict) -> str:
    lines = [f"Active jobs in database: {ctx['total_jobs']}",
             f"Pipeline: {ctx['pipeline'] or 'no applications yet'}"]
    if ctx["top_matches"]:
        lines.append("Top matches:")
        lines += [f"  - {m['title']} (score {m['score']:.0f})" for m in ctx["top_matches"]]
    return "\n".join(lines)


def _rule_answer(question: str, ctx: dict) -> str:
    q = question.lower()
    pipe = ctx["pipeline"]
    if re.search(r"\b(status|how many|progress|summary|this week)\b", q):
        applied = pipe.get("APPLIED", 0)
        interviews = pipe.get("INTERVIEW_SCHEDULED", 0)
        return (f"You have {ctx['total_jobs']} active jobs tracked, {applied} "
                f"applications submitted, and {interviews} interviews scheduled.")
    if re.search(r"\b(top|best|match|apply)\b", q):
        if not ctx["top_matches"]:
            return "No scored matches yet — run a job search first."
        return "Your best matches right now:\n" + "\n".join(
            f"- {m['title']} (score {m['score']:.0f}) — {m['url']}"
            for m in ctx["top_matches"])
    if re.search(r"\b(missing|skill|gap|improve)\b", q):
        return ("Open a specific job to see its skill-gap breakdown, or ask me to "
                "tailor your resume for one.")
    return ("I can report your pipeline status, surface your top matches, explain "
            "why a job scored the way it did, or tailor your resume. What would "
            "you like?")


def detect_action(question: str) -> str | None:
    for pattern, action in _INTENT_ACTION:
        if pattern.search(question):
            return action
    return None


async def ask(session: AsyncSession, user_id: uuid.UUID,
              conversation_id: uuid.UUID, question: str) -> AssistantReply:
    ctx = await _context(session, user_id)
    action = detect_action(question)

    model = None
    try:
        from app.ai.gateway import AiGateway
        res = AiGateway().chat([
            {"role": "system", "content":
                "You are Jarvis, a concise assistant managing the user's job "
                "search. Answer ONLY from the data snapshot; if it's not there, "
                "say so. Under 120 words."},
            {"role": "user", "content":
                f"DATA:\n{_render_context(ctx)}\n\nQUESTION: {question}"},
        ], max_tokens=300)
        content, model = res.text.strip(), res.model
    except Exception:  # noqa: BLE001 — AiUnavailable or transport error
        content = _rule_answer(question, ctx)

    session.add(AiMessage(conversation_id=conversation_id, role="USER",
                          content=question))
    session.add(AiMessage(conversation_id=conversation_id, role="ASSISTANT",
                          content=content))
    return AssistantReply(content=content, action=action, model=model)


async def create_conversation(session: AsyncSession, user_id: uuid.UUID,
                              title: str | None) -> AiConversation:
    conv = AiConversation(user_id=user_id, title=title or "New conversation")
    session.add(conv)
    await session.flush()
    return conv
