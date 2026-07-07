"""AI job extraction — pull structured facts (skills, tech stack, salary,
responsibilities, seniority, sponsorship, recruiter) from a JD.

Uses the AI gateway when available; falls back to the deterministic
heuristics already proven in the ingestion normalizer, so extraction always
produces a result."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import structlog

from app.ingestion.normalize import classify_seniority, classify_sponsorship

from .gateway import AiGateway, AiUnavailable

log = structlog.get_logger("ai.extraction")

# A compact, common tech vocabulary for the heuristic fallback.
_TECH_VOCAB = [
    "Python", "Java", "JavaScript", "TypeScript", "Go", "Rust", "C++", "C#",
    "Ruby", "Scala", "Kotlin", "SQL", "PostgreSQL", "MySQL", "MongoDB",
    "Redis", "Kafka", "Spark", "Airflow", "Snowflake", "AWS", "Azure", "GCP",
    "Docker", "Kubernetes", "Terraform", "React", "Angular", "Vue", "Node.js",
    "Spring Boot", "Django", "FastAPI", "Flask", "GraphQL", "REST", "gRPC",
    "Microservices", "CI/CD", "Machine Learning", "TensorFlow", "PyTorch",
    "Pandas", "Jenkins", "Git",
]
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_RECRUITER = re.compile(
    r"(?:recruiter|contact|reach out to)\s*[:\-]?\s*"
    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})")


@dataclass
class Extraction:
    skills: list[str] = field(default_factory=list)
    tech_stack: list[str] = field(default_factory=list)
    responsibilities: list[str] = field(default_factory=list)
    benefits: list[str] = field(default_factory=list)
    sponsorship: str = "UNKNOWN"
    seniority: str = "UNKNOWN"
    recruiter_name: str | None = None
    recruiter_contact: str | None = None
    method: str = "HEURISTIC"


def _heuristic(title: str, description: str) -> Extraction:
    found = [t for t in _TECH_VOCAB
             if re.search(rf"\b{re.escape(t)}\b", description, re.I)]
    email = _EMAIL.search(description)
    name = _RECRUITER.search(description)
    return Extraction(
        skills=found, tech_stack=found,
        sponsorship=classify_sponsorship(description),
        seniority=classify_seniority(title, description),
        recruiter_name=name.group(1) if name else None,
        recruiter_contact=email.group(0) if email else None,
        method="HEURISTIC")


def extract(title: str, description: str,
            gateway: AiGateway | None = None) -> Extraction:
    gateway = gateway or AiGateway()
    heuristic = _heuristic(title, description)
    if not description.strip():
        return heuristic
    try:
        data = gateway.chat_json([
            {"role": "system", "content":
                "You extract structured facts from a job description. Return JSON "
                "with keys: skills (array), tech_stack (array), responsibilities "
                "(array of short strings), benefits (array), seniority (one of "
                "ENTRY,MID,SENIOR,LEAD,PRINCIPAL), sponsorship (one of "
                "SPONSOR_FRIENDLY,NO_SPONSOR,UNKNOWN), recruiter_name (string or "
                "null), recruiter_contact (email/url or null). Only facts present "
                "in the text."},
            {"role": "user", "content": f"Title: {title}\n\n{description[:6000]}"},
        ], max_tokens=700)
    except AiUnavailable:
        return heuristic

    def _arr(key):
        v = data.get(key)
        return [str(x) for x in v] if isinstance(v, list) else []

    seniority = str(data.get("seniority", "")).upper()
    sponsorship = str(data.get("sponsorship", "")).upper()
    return Extraction(
        skills=_arr("skills") or heuristic.skills,
        tech_stack=_arr("tech_stack") or heuristic.tech_stack,
        responsibilities=_arr("responsibilities"),
        benefits=_arr("benefits"),
        sponsorship=sponsorship if sponsorship in
        ("SPONSOR_FRIENDLY", "NO_SPONSOR", "UNKNOWN") else heuristic.sponsorship,
        seniority=seniority if seniority in
        ("ENTRY", "MID", "SENIOR", "LEAD", "PRINCIPAL") else heuristic.seniority,
        recruiter_name=data.get("recruiter_name") or heuristic.recruiter_name,
        recruiter_contact=data.get("recruiter_contact") or heuristic.recruiter_contact,
        method="LLM")
