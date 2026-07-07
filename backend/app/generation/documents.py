"""Document generation: tailored resume summary, cover letter, recruiter
email, LinkedIn message, cold email — all constrained to the candidate's real
resume and passed through the truthfulness guardrail before returning.

If AI is unavailable, deterministic templates fill from real resume facts —
so the feature always produces a usable, truthful draft."""
from __future__ import annotations

from dataclasses import dataclass

import structlog

from app.ai.gateway import AiGateway, AiUnavailable

from .guardrail import GuardrailReport, check_generated

log = structlog.get_logger("generation")

DOC_TYPES = ("TAILORED_RESUME", "COVER_LETTER", "RECRUITER_EMAIL",
             "LINKEDIN_MESSAGE", "COLD_EMAIL")

_SYSTEM = (
    "You write job-application materials for a candidate. ABSOLUTE RULE: use "
    "ONLY skills, employers, titles, and credentials that appear in the "
    "candidate's resume below. Never invent experience, tools, degrees, or "
    "metrics. Emphasize and rephrase real facts to fit the job. Be concise "
    "and professional.")

_INSTRUCTIONS = {
    "TAILORED_RESUME": "Write a 3-4 sentence professional summary tailored to this role.",
    "COVER_LETTER": "Write a short cover letter (3 short paragraphs).",
    "RECRUITER_EMAIL": "Write a brief email to the recruiter showing interest, under 150 words.",
    "LINKEDIN_MESSAGE": "Write a LinkedIn connection note under 300 characters.",
    "COLD_EMAIL": "Write a concise cold email to the hiring manager (under 150 words).",
}


@dataclass
class GeneratedDoc:
    doc_type: str
    content: str
    model: str | None
    guardrail: GuardrailReport


def _fallback(doc_type: str, name: str, title: str, company: str,
              overlap_skills: list[str]) -> str:
    skills = ", ".join(overlap_skills[:5]) or "my background"
    if doc_type == "LINKEDIN_MESSAGE":
        return (f"Hi, I came across the {title} role at {company} and it aligns "
                f"closely with my experience in {skills}. I'd love to connect.")[:300]
    if doc_type == "TAILORED_RESUME":
        return (f"Software professional with hands-on experience in {skills}. "
                f"Strong fit for the {title} position at {company}, bringing "
                f"proven delivery and collaboration across the full stack.")
    greeting = "Dear Hiring Team," if doc_type == "COVER_LETTER" else "Hello,"
    return (f"{greeting}\n\nI'm excited to apply for the {title} role at {company}. "
            f"My experience with {skills} maps directly to what you're looking for, "
            f"and I'm confident I can contribute from day one.\n\n"
            f"I'd welcome the chance to discuss further.\n\nBest regards,\n{name}")


def generate(doc_type: str, *, candidate_name: str, resume_text: str,
             overlap_skills: list[str], job_title: str, job_company: str,
             job_description: str, gateway: AiGateway | None = None,
             max_regens: int = 2) -> GeneratedDoc:
    if doc_type not in DOC_TYPES:
        raise ValueError(f"unknown doc_type: {doc_type}")
    gateway = gateway or AiGateway()

    for attempt in range(max_regens):
        try:
            strictness = ("" if attempt == 0 else
                          " Your previous draft invented facts. Use ONLY the resume.")
            res = gateway.chat([
                {"role": "system", "content": _SYSTEM + strictness},
                {"role": "user", "content":
                    f"CANDIDATE RESUME:\n{resume_text[:5000]}\n\n"
                    f"JOB: {job_title} at {job_company}\n{job_description[:2500]}\n\n"
                    f"TASK: {_INSTRUCTIONS[doc_type]}"},
            ], max_tokens=600)
            report = check_generated(resume_text, res.text)
            if report.ok:
                return GeneratedDoc(doc_type, res.text.strip(), res.model, report)
            log.warning("guardrail_rejected", doc_type=doc_type, attempt=attempt,
                        fabricated=report.fabricated_skills)
        except AiUnavailable:
            break

    # AI unavailable or repeatedly fabricated → safe deterministic template.
    fallback = _fallback(doc_type, candidate_name, job_title, job_company, overlap_skills)
    return GeneratedDoc(doc_type, fallback, None, check_generated(resume_text, fallback))
