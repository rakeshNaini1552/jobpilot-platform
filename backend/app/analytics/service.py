"""Analytics: dashboard KPIs, funnel, distributions, hiring trends,
tech demand — all computed in SQL over the user's data."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import Integer, case, cast, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.models import Application
from app.connector.models import Company, Job, JobExtraction
from app.matching.models import MatchScore

_TERMINAL_APPLIED = ("APPLIED", "RECRUITER_CONTACTED", "OA_RECEIVED",
                     "INTERVIEW_SCHEDULED", "REJECTED", "OFFER", "ACCEPTED",
                     "DECLINED")


async def dashboard(session: AsyncSession, user_id: uuid.UUID) -> dict:
    jobs_found = await session.scalar(
        select(func.count()).select_from(Job).where(Job.status == "ACTIVE")) or 0

    funnel_rows = (await session.execute(
        select(Application.status, func.count())
        .where(Application.user_id == user_id, Application.deleted_at.is_(None))
        .group_by(Application.status))).all()
    funnel = {status: n for status, n in funnel_rows}

    applied = sum(funnel.get(s, 0) for s in _TERMINAL_APPLIED)
    interviews = funnel.get("INTERVIEW_SCHEDULED", 0)
    offers = funnel.get("OFFER", 0) + funnel.get("ACCEPTED", 0)
    rejections = funnel.get("REJECTED", 0)
    responded = interviews + offers + funnel.get("OA_RECEIVED", 0)

    by_week = (await session.execute(
        select(func.to_char(func.date_trunc("week", Application.applied_at),
                            text("'YYYY-MM-DD'")).label("week"),
               func.count())
        .where(Application.user_id == user_id,
               Application.applied_at.isnot(None))
        .group_by(text("week")).order_by(text("week")))).all()

    by_company = (await session.execute(
        select(Company.name, func.count())
        .join(Job, Job.company_id == Company.id)
        .join(Application, Application.job_id == Job.id)
        .where(Application.user_id == user_id, Application.deleted_at.is_(None))
        .group_by(Company.name).order_by(func.count().desc()).limit(10))).all()

    score_bucket = cast(func.floor(MatchScore.overall / 10) * 10, Integer)
    score_dist = (await session.execute(
        select(score_bucket.label("bucket"), func.count())
        .where(MatchScore.user_id == user_id)
        .group_by(text("bucket")).order_by(text("bucket")))).all()

    salary_bucket = cast(func.floor(Job.salary_max / 25000) * 25000, Integer)
    salary_dist = (await session.execute(
        select(salary_bucket.label("bucket"), func.count())
        .where(Job.status == "ACTIVE", Job.salary_max.isnot(None))
        .group_by(text("bucket")).order_by(text("bucket")))).all()

    top = (await session.execute(
        select(Job.title, Job.url, MatchScore.overall)
        .join(MatchScore, MatchScore.job_id == Job.id)
        .where(MatchScore.user_id == user_id, Job.status == "ACTIVE")
        .order_by(MatchScore.overall.desc()).limit(10))).all()

    # Deterministic AI-style suggestions from real gaps.
    missing = (await session.execute(text(
        "SELECT gap->>'skill' AS skill, count(*) AS n "
        "FROM match_scores, jsonb_array_elements(skill_gap) AS gap "
        "WHERE user_id = :uid AND (gap->>'have')::boolean = false "
        "GROUP BY 1 ORDER BY n DESC LIMIT 3"), {"uid": str(user_id)})).all()
    suggestions = [f"'{skill}' appears in {n} matched jobs but not on your "
                   f"resume — add it if you have real experience."
                   for skill, n in missing]
    if applied and not responded:
        suggestions.append("No responses yet — consider recruiter outreach "
                           "on your top matches.")

    return {
        "jobs_found": jobs_found,
        "jobs_applied": applied,
        "interviews": interviews,
        "rejections": rejections,
        "offers": offers,
        "success_rate": round(100 * offers / applied, 1) if applied else 0.0,
        "recruiter_response_rate": round(100 * responded / applied, 1) if applied else 0.0,
        "applications_by_week": [{"week": w, "count": n} for w, n in by_week],
        "applications_by_company": [{"company": c, "count": n} for c, n in by_company],
        "match_score_distribution": [{"bucket": f"{b}-{b+9}", "count": n}
                                     for b, n in score_dist],
        "salary_distribution": [{"bucket": f"{b//1000}k", "count": n}
                                for b, n in salary_dist],
        "funnel": [{"status": s, "count": n} for s, n in funnel_rows],
        "ai_suggestions": suggestions,
        "top_matches": [{"title": t, "url": u, "score": float(s)}
                        for t, u, s in top],
    }


async def trends(session: AsyncSession, user_id: uuid.UUID,
                 days: int = 30) -> dict:
    cutoff = datetime.now(UTC) - timedelta(days=days)
    half = datetime.now(UTC) - timedelta(days=days / 2)

    per_day = (await session.execute(
        select(func.to_char(func.date_trunc("day", Job.first_seen_at),
                            text("'YYYY-MM-DD'")).label("d"), func.count())
        .where(Job.first_seen_at >= cutoff)
        .group_by(text("d")).order_by(text("d")))).all()

    recent = func.sum(case((Job.first_seen_at >= half, 1), else_=0))
    previous = func.sum(case((Job.first_seen_at < half, 1), else_=0))
    booming = (await session.execute(
        select(Company.name, recent.label("recent"), previous.label("previous"))
        .join(Job, Job.company_id == Company.id)
        .where(Job.first_seen_at >= cutoff)
        .group_by(Company.name)
        .order_by(recent.desc()).limit(10))).all()

    demand = (await session.execute(
        select(func.unnest(JobExtraction.skills).label("skill"), func.count())
        .select_from(JobExtraction)
        .join(Job, Job.id == JobExtraction.job_id)
        .where(Job.first_seen_at >= cutoff)
        .group_by(text("skill")).order_by(func.count().desc()).limit(15))).all()

    return {
        "postings_per_day": [{"date": d, "count": n} for d, n in per_day],
        "booming_companies": [
            {"company": c, "recent": int(r or 0), "previous": int(p or 0),
             "growth_pct": round(100 * ((r or 0) - (p or 0)) / max(p or 0, 1))}
            for c, r, p in booming],
        "tech_demand": [{"skill": s, "count": n} for s, n in demand],
    }
