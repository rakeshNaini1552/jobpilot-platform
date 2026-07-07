"""Canonicalize raw postings into persisted jobs + companies, with dedupe.

Dedupe strategy (mirrors the DB unique constraints):
  - dedupe_hash = sha1 of the canonical URL when present, else title+company.
  - companies collapse on a normalized name (lowercased, suffix-stripped).
Extraction here is deterministic/heuristic (the AI enricher in Phase 8
refines it); this keeps ingestion working with zero AI configured.
"""
import hashlib
import re
from datetime import datetime

from dateutil import parser as dateparser
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connector.models import Company, Job, JobExtraction
from app.connector.spi import RawPosting, guess_arrangement, guess_employment, guess_workplace

_SUFFIX = re.compile(r"\b(inc|llc|ltd|limited|corp|co|gmbh|plc|pvt|technologies|"
                     r"solutions|systems|consulting|staffing)\b\.?", re.I)
_NONWORD = re.compile(r"[^a-z0-9]+")
_URL_TRACKING = re.compile(r"[?#].*$")

_NO_SPONSOR = re.compile(
    r"(no sponsorship|not (?:able|available) to sponsor|unable to sponsor|"
    r"cannot sponsor|will not sponsor|without sponsorship|us citizens? only|"
    r"gc (?:holders? )?only|green card (?:holders? )?(?:and citizens? )?only)", re.I)
_SPONSOR_OK = re.compile(
    r"(visa sponsorship (?:is )?available|sponsorship available|will sponsor|"
    r"h-?1b (?:transfer|sponsorship)|open to sponsorship)", re.I)

_SENIORITY = [
    ("PRINCIPAL", re.compile(r"\b(principal|staff|architect|distinguished)\b", re.I)),
    ("LEAD", re.compile(r"\b(lead|manager|head of)\b", re.I)),
    ("SENIOR", re.compile(r"\b(senior|sr\.?)\b", re.I)),
    ("ENTRY", re.compile(r"\b(junior|jr\.?|entry|new grad|graduate|associate)\b", re.I)),
]


def normalize_company_name(name: str) -> str:
    base = _SUFFIX.sub("", (name or "").lower())
    return _NONWORD.sub(" ", base).strip() or (name or "").lower().strip()


def canonical_url(url: str) -> str:
    return _URL_TRACKING.sub("", (url or "").strip().rstrip("/"))


def dedupe_hash(posting: RawPosting) -> str:
    if posting.url:
        key = canonical_url(posting.url).lower()
    else:
        key = f"{posting.title.lower()}|{normalize_company_name(posting.company_name)}"
    return hashlib.sha1(key.encode()).hexdigest()


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return dateparser.parse(value)
    except (ValueError, OverflowError):
        return None


def classify_sponsorship(text: str) -> str:
    if not text:
        return "UNKNOWN"
    if _NO_SPONSOR.search(text):
        return "NO_SPONSOR"
    if _SPONSOR_OK.search(text):
        return "SPONSOR_FRIENDLY"
    return "UNKNOWN"


def classify_seniority(title: str, description: str) -> str:
    hay = f"{title} {description[:400]}"
    for level, pattern in _SENIORITY:
        if pattern.search(hay):
            return level
    return "MID"


def get_or_create_company(session: Session, name: str) -> Company | None:
    if not name.strip():
        return None
    norm = normalize_company_name(name)
    company = session.scalar(select(Company).where(Company.normalized_name == norm))
    if company is None:
        company = Company(name=name.strip(), normalized_name=norm)
        session.add(company)
        session.flush()
    return company


def upsert_job(session: Session, posting: RawPosting) -> tuple[Job, bool]:
    """Insert or refresh a job. Returns (job, is_new)."""
    dh = dedupe_hash(posting)
    existing = session.scalar(select(Job).where(Job.dedupe_hash == dh))
    if existing:
        existing.last_seen_at = datetime.now()
        return existing, False

    company = get_or_create_company(session, posting.company_name)
    text = f"{posting.title}\n{posting.description_md}"
    job = Job(
        connector_id=posting.connector_id,
        external_id=posting.external_id,
        company_id=company.id if company else None,
        title=posting.title.strip(),
        description_md=posting.description_md,
        url=posting.url,
        dedupe_hash=dh,
        location_text=posting.location_text,
        city=posting.city, state=posting.state,
        country=(posting.country or None) and posting.country[:2].upper(),
        workplace=guess_workplace(posting.location_text + " " + posting.description_md,
                                  posting.is_remote),
        employment=guess_employment(posting.employment_raw or text),
        arrangement=guess_arrangement(text),
        salary_min=posting.salary_min, salary_max=posting.salary_max,
        salary_currency=posting.salary_currency, salary_period=posting.salary_period,
        posted_at=_parse_dt(posting.posted_at),
        raw=posting.raw or {},
    )
    session.add(job)
    session.flush()

    session.add(JobExtraction(
        job_id=job.id,
        sponsorship=classify_sponsorship(text),
        seniority=classify_seniority(posting.title, posting.description_md),
        method="HEURISTIC",
    ))
    return job, True
