"""Match engine — hybrid scoring of a job against a resume + preferences.

Every sub-score is deterministic and persisted, so "why was this ranked low?"
is always answerable without an LLM. When AI is available it adds a short
natural-language rationale on top; it never overrides the numbers.

Sub-scores (0..100), combined by weight into `overall`:
  resume_pct   — resume skills ∩ job skills
  ats_pct      — JD keyword coverage in the resume text
  salary_score — job salary vs the user's expectation
  location_score — workplace/location vs preferences
  visa_score   — sponsorship posture vs the user's need
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.ai.extraction import Extraction

_WEIGHTS = {"resume_pct": 0.35, "ats_pct": 0.20, "salary_score": 0.15,
            "location_score": 0.15, "visa_score": 0.15}
_WORD = re.compile(r"[a-z0-9+#.]+")


@dataclass
class MatchInput:
    job_title: str
    job_workplace: str          # REMOTE/HYBRID/ONSITE/UNKNOWN
    job_salary_min: int | None
    job_salary_max: int | None
    extraction: Extraction
    resume_skills: list[str]
    resume_text: str
    pref_salary_min: int | None = None
    pref_workplace: list[str] = field(default_factory=list)
    needs_sponsorship: bool = False


@dataclass
class MatchResult:
    overall: float
    resume_pct: float
    ats_pct: float
    salary_score: float
    location_score: float
    visa_score: float
    skill_gap: list[dict]
    reasoning: str | None = None
    model: str | None = None


def _tokens(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def _skill_overlap(resume_skills: list[str], job_skills: list[str]) -> tuple[float, list[dict]]:
    if not job_skills:
        return 60.0, []                       # no stated requirements → neutral
    have = {s.lower() for s in resume_skills}
    gap = []
    matched = 0
    for skill in job_skills:
        present = skill.lower() in have
        matched += present
        gap.append({"skill": skill, "required": True, "have": present})
    return round(100 * matched / len(job_skills), 2), gap


def _ats_coverage(resume_text: str, job_skills: list[str]) -> float:
    if not job_skills:
        return 60.0
    tokens = _tokens(resume_text)
    hits = sum(1 for s in job_skills if s.lower() in tokens
               or any(part in tokens for part in s.lower().split()))
    return round(100 * hits / len(job_skills), 2)


def _salary_fit(job_min: int | None, job_max: int | None,
                pref_min: int | None) -> float:
    if not pref_min:
        return 60.0
    top = job_max or job_min
    if not top:
        return 50.0                           # unknown salary → mild neutral
    if top >= pref_min:
        return 100.0
    return round(max(0.0, 100 * top / pref_min), 2)


def _location_fit(job_workplace: str, pref_workplace: list[str]) -> float:
    if not pref_workplace or job_workplace == "UNKNOWN":
        return 60.0
    return 100.0 if job_workplace in pref_workplace else 30.0


def _visa_fit(needs_sponsorship: bool, sponsorship: str) -> float:
    if not needs_sponsorship:
        return 100.0                          # no need → never penalized
    return {"SPONSOR_FRIENDLY": 100.0, "UNKNOWN": 55.0, "NO_SPONSOR": 0.0}[sponsorship]


def score(inp: MatchInput) -> MatchResult:
    resume_pct, gap = _skill_overlap(inp.resume_skills, inp.extraction.skills)
    ats_pct = _ats_coverage(inp.resume_text, inp.extraction.skills)
    salary_score = _salary_fit(inp.job_salary_min, inp.job_salary_max, inp.pref_salary_min)
    location_score = _location_fit(inp.job_workplace, inp.pref_workplace)
    visa_score = _visa_fit(inp.needs_sponsorship, inp.extraction.sponsorship)

    parts = {"resume_pct": resume_pct, "ats_pct": ats_pct,
             "salary_score": salary_score, "location_score": location_score,
             "visa_score": visa_score}
    overall = round(sum(parts[k] * w for k, w in _WEIGHTS.items()), 2)
    return MatchResult(overall=overall, skill_gap=gap, **parts)


def add_reasoning(result: MatchResult, inp: MatchInput, gateway=None) -> MatchResult:
    """Optionally attach a one-paragraph rationale. Never changes the score."""
    from app.ai.gateway import AiGateway, AiUnavailable
    gateway = gateway or AiGateway()
    missing = [g["skill"] for g in result.skill_gap if not g["have"]]
    try:
        res = gateway.chat([
            {"role": "system", "content":
                "You explain a job match score in 2-3 sentences, grounded only in "
                "the provided numbers. Be direct about weaknesses."},
            {"role": "user", "content":
                f"Role: {inp.job_title}. Overall {result.overall}/100. "
                f"Resume skill match {result.resume_pct}%, ATS {result.ats_pct}%, "
                f"salary {result.salary_score}, location {result.location_score}, "
                f"visa {result.visa_score}. Missing skills: {', '.join(missing) or 'none'}."},
        ], max_tokens=200)
        result.reasoning = res.text.strip()
        result.model = res.model
    except AiUnavailable:
        top_gap = f" Missing: {', '.join(missing[:5])}." if missing else ""
        result.reasoning = (
            f"Overall {result.overall}/100 — resume skills match "
            f"{result.resume_pct}%, keyword coverage {result.ats_pct}%.{top_gap}")
    return result
