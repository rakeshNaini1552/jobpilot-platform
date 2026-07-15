"""Daily report builder — gathers the day's numbers for one user (sync,
worker-side) and renders the email HTML via Jinja2."""
from datetime import UTC, datetime, timedelta
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.application.models import Application
from app.connector.models import Company, Job
from app.matching.models import MatchScore
from app.user.models import User

_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=select_autoescape(["html"]),
)

_RESPONDED = ("OA_RECEIVED", "INTERVIEW_SCHEDULED", "OFFER", "ACCEPTED")


def build_daily_report(session: Session, user: User,
                       app_url: str = "http://localhost:5173") -> dict:
    """Returns {subject, html, payload} for the user's daily email."""
    since = datetime.now(UTC) - timedelta(hours=24)

    new_jobs = session.execute(
        select(Job.title, Job.url, Company.name, MatchScore.overall)
        .join(MatchScore, MatchScore.job_id == Job.id)
        .outerjoin(Company, Company.id == Job.company_id)
        .where(MatchScore.user_id == user.id, Job.first_seen_at >= since,
               Job.status == "ACTIVE")
        .order_by(MatchScore.overall.desc()).limit(10)).all()

    pipeline = dict(session.execute(
        select(Application.status, func.count())
        .where(Application.user_id == user.id, Application.deleted_at.is_(None))
        .group_by(Application.status)).all())

    applied_today = session.scalar(
        select(func.count()).select_from(Application)
        .where(Application.user_id == user.id,
               Application.applied_at >= since)) or 0

    interviews = pipeline.get("INTERVIEW_SCHEDULED", 0)
    offers = pipeline.get("OFFER", 0) + pipeline.get("ACCEPTED", 0)

    actions = []
    if new_jobs:
        best = new_jobs[0]
        actions.append(f"Review '{best[0]}' at {best[2] or 'unknown'} "
                       f"(score {float(best[3]):.0f}) — your strongest new match.")
    stale = pipeline.get("APPLIED", 0)
    if stale and not interviews:
        actions.append(f"{stale} applications await responses — consider a "
                       f"follow-up or recruiter message.")
    if not new_jobs and not applied_today:
        actions.append("Quiet day. Broaden desired titles or add companies "
                       "to your watchlist to widen the funnel.")

    kpis = [
        {"label": "New matches", "value": len(new_jobs)},
        {"label": "Applied today", "value": applied_today},
        {"label": "Interviews", "value": interviews},
        {"label": "Offers", "value": offers},
    ]
    payload = {
        "date": datetime.now(UTC).strftime("%b %d, %Y"),
        "name": user.full_name.split()[0] if user.full_name else "there",
        "kpis": kpis,
        "new_jobs": [{"title": t, "url": u, "company": c or "—",
                      "score": f"{float(s):.0f}"} for t, u, c, s in new_jobs],
        "actions": actions,
        "app_url": app_url,
        "report_hour": 21,
    }
    html = _env.get_template("daily_report.html").render(**payload)
    subject = (f"JobPilot: {len(new_jobs)} new matches, "
               f"{applied_today} applied — {payload['date']}")
    return {"subject": subject, "html": html, "payload": payload}
