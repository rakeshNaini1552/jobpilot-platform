"""Connector SPI — the contract every job source implements, plus the
normalized posting the pipeline consumes.

Compliance is a framework property, not a per-connector promise: the
descriptor declares a mode, and the ingestion layer + registry enforce what
is allowed (rate limits, honest UA, robots, no automation on SEARCH_LINK).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable


class ComplianceMode(StrEnum):
    OFFICIAL_API = "OFFICIAL_API"
    PUBLIC_FEED = "PUBLIC_FEED"
    SEARCH_LINK = "SEARCH_LINK"
    USER_AUTHORIZED_AUTOMATION = "USER_AUTHORIZED_AUTOMATION"


@dataclass(frozen=True)
class ConnectorDescriptor:
    id: str
    display_name: str
    compliance_mode: ComplianceMode
    rate_limit_per_min: int = 30
    # Only OFFICIAL_API / USER_AUTHORIZED_AUTOMATION may ever auto-apply.
    supports_auto_apply: bool = False


@dataclass
class ConnectorConfig:
    """Per-source config (API keys, ATS slug, base URL). Values that are
    secret are stored encrypted in connector_settings.config and decrypted
    by the registry before handing them here."""
    enabled: bool = True
    rate_limit_per_min: int = 30
    options: dict = field(default_factory=dict)


@dataclass
class JobQuery:
    """Normalized search intent derived from a user's preferences."""
    terms: list[str] = field(default_factory=list)
    location: str | None = None
    country: str = "US"
    remote: bool | None = None
    employment_types: list[str] = field(default_factory=list)
    posted_within_hours: int = 168
    limit: int = 50


@dataclass
class RawPosting:
    """What a connector emits. The normalizer canonicalizes and dedupes it
    before it becomes a `jobs` row."""
    connector_id: str
    title: str
    company_name: str
    url: str
    external_id: str | None = None
    description_md: str = ""
    location_text: str = ""
    city: str | None = None
    state: str | None = None
    country: str | None = None
    is_remote: bool | None = None
    employment_raw: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    salary_period: str | None = None
    posted_at: str | None = None
    raw: dict = field(default_factory=dict)


@runtime_checkable
class JobSourceConnector(Protocol):
    descriptor: ConnectorDescriptor

    def is_configured(self, cfg: ConnectorConfig) -> bool: ...

    def search(self, query: JobQuery, cfg: ConnectorConfig) -> list[RawPosting]: ...


class SearchLinkConnector(Protocol):
    """SEARCH_LINK sources don't scrape; they build compliant search URLs the
    user opens themselves (export flow)."""
    descriptor: ConnectorDescriptor

    def build_urls(self, query: JobQuery, cfg: ConnectorConfig) -> list[dict]: ...


# --- shared helpers connectors reuse ---------------------------------------

_C2C = re.compile(r"\b(c2c|corp[\s-]*to[\s-]*corp|third[\s-]*party)\b", re.I)
_W2 = re.compile(r"\bw[\s-]?2\b", re.I)
_1099 = re.compile(r"\b1099\b")


def guess_employment(text: str | None, fallback: str = "UNKNOWN") -> str:
    if not text:
        return fallback
    t = text.lower()
    if "intern" in t:
        return "INTERNSHIP"
    if "part" in t and "time" in t:
        return "PART_TIME"
    if "contract" in t or "contractor" in t or _C2C.search(t) or _W2.search(t):
        return "CONTRACT"
    if "full" in t and "time" in t:
        return "FULL_TIME"
    return fallback


# "No C2C", "C2C not accepted", "W2 only" must NOT classify as C2C.
_NEG_C2C = re.compile(
    r"\b(?:no|not|without|cannot|can't|won't|don'?t)\s+(?:accept\w*\s+|work\s+with\s+|do\s+)?"
    r"(?:c2c|corp[\s-]*to[\s-]*corp|third[\s-]*party)", re.I)
_W2_ONLY = re.compile(r"\bw[\s-]?2\s*(?:only|basis|candidates?\s+only)\b", re.I)


def guess_arrangement(text: str | None, employment_raw: str | None = None) -> str:
    """Classify W2 / 1099 / C2C.

    The source's own employment-type field (e.g. Dice's
    'Contract Corp-To-Corp, Contract W2') is authoritative when present;
    free text is only consulted after negations are handled — many postings
    mention C2C precisely to say they DON'T take it."""
    if employment_raw:
        raw = employment_raw.lower()
        if _C2C.search(raw):
            return "C2C"
        if _1099.search(raw) or "independent" in raw:
            return "C1099"
        if _W2.search(raw):
            return "W2"

    if not text:
        return "UNSPECIFIED"
    negated_c2c = bool(_NEG_C2C.search(text) or _W2_ONLY.search(text))
    c2c = bool(_C2C.search(text)) and not negated_c2c
    if c2c:
        return "C2C"
    if _1099.search(text):
        return "C1099"
    if _W2.search(text) or negated_c2c:
        return "W2"
    return "UNSPECIFIED"


def guess_workplace(text: str | None, is_remote: bool | None) -> str:
    if is_remote is True:
        return "REMOTE"
    if not text:
        return "UNKNOWN"
    t = text.lower()
    if "hybrid" in t:
        return "HYBRID"
    if "remote" in t:
        return "REMOTE"
    if "on-site" in t or "onsite" in t or "in office" in t:
        return "ONSITE"
    return "UNKNOWN"
