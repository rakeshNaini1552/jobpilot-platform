"""Keyless PUBLIC_FEED connectors beyond Dice: RemoteOK and Remotive.

Both publish official public JSON APIs intended for exactly this use
(RemoteOK requires linking back to the posting URL, which we always do —
the stored `url` IS the RemoteOK link). Remote-only inventory, so they
surface results whenever the user is open to remote work."""
import re

from app.connector.http import get_json
from app.connector.spi import (
    ComplianceMode,
    ConnectorConfig,
    ConnectorDescriptor,
    JobQuery,
    RawPosting,
)

_TAGS = re.compile(r"<[^>]+>")


def _strip_html(html: str) -> str:
    return _TAGS.sub(" ", html or "").strip()


# Remote boards title loosely ("Backend Engineer (Java)"), so an exact
# phrase match starves results. Match the term's distinctive words instead.
_GENERIC_WORDS = {"developer", "engineer", "engineering", "senior", "junior",
                  "lead", "staff", "sr", "jr", "the", "and", "of"}
_WORD = re.compile(r"[a-z0-9+#.]+")


def _matches(query: JobQuery, title: str, extra: str = "") -> bool:
    if not query.terms:
        return True
    hay = f"{title} {extra}".lower()
    tokens = set(_WORD.findall(hay))          # whole words: java ≠ javascript
    for term in query.terms:
        t = term.lower()
        if t in hay:
            return True
        distinctive = [w for w in _WORD.findall(t) if w not in _GENERIC_WORDS]
        if distinctive and all(w in tokens for w in distinctive):
            return True
    return False


class RemoteOKConnector:
    descriptor = ConnectorDescriptor(
        "remoteok", "RemoteOK public API",
        ComplianceMode.PUBLIC_FEED, rate_limit_per_min=10, supports_auto_apply=False)

    def is_configured(self, cfg: ConnectorConfig) -> bool:
        return True

    def search(self, query: JobQuery, cfg: ConnectorConfig) -> list[RawPosting]:
        data = get_json(self.descriptor.id, "https://remoteok.com/api",
                        per_min=cfg.rate_limit_per_min)
        if not isinstance(data, list):
            return []
        out = []
        for j in data:
            # element 0 is RemoteOK's legal notice, not a job
            if not isinstance(j, dict) or not j.get("position"):
                continue
            if not _matches(query, j.get("position", ""),
                            extra=" ".join(j.get("tags") or [])):
                continue
            out.append(RawPosting(
                connector_id=self.descriptor.id, external_id=str(j.get("id")),
                title=j.get("position", ""), company_name=j.get("company", ""),
                url=j.get("url", ""),
                description_md=_strip_html(j.get("description", ""))[:8000],
                location_text=j.get("location") or "Remote",
                is_remote=True,
                salary_min=j.get("salary_min") or None,
                salary_max=j.get("salary_max") or None,
                salary_currency="USD" if j.get("salary_min") else None,
                posted_at=j.get("date"),
                raw={"remoteok_id": j.get("id"), "tags": j.get("tags", [])}))
        return out[: query.limit]


class RemotiveConnector:
    descriptor = ConnectorDescriptor(
        "remotive", "Remotive public API",
        ComplianceMode.PUBLIC_FEED, rate_limit_per_min=10, supports_auto_apply=False)

    def is_configured(self, cfg: ConnectorConfig) -> bool:
        return True

    def search(self, query: JobQuery, cfg: ConnectorConfig) -> list[RawPosting]:
        params = {"limit": min(query.limit, 50)}
        if query.terms:
            params["search"] = query.terms[0]
        data = get_json(self.descriptor.id, "https://remotive.com/api/remote-jobs",
                        params=params, per_min=cfg.rate_limit_per_min)
        if not isinstance(data, dict):
            return []
        out = []
        for j in data.get("jobs", []):
            if not _matches(query, j.get("title", "")):
                continue
            out.append(RawPosting(
                connector_id=self.descriptor.id, external_id=str(j.get("id")),
                title=j.get("title", ""), company_name=j.get("company_name", ""),
                url=j.get("url", ""),
                description_md=_strip_html(j.get("description", ""))[:8000],
                location_text=j.get("candidate_required_location") or "Remote",
                is_remote=True,
                employment_raw=j.get("job_type"),
                posted_at=j.get("publication_date"),
                raw={"remotive_id": j.get("id"), "category": j.get("category")}))
        return out[: query.limit]
