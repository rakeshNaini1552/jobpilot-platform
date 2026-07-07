"""OFFICIAL_API connectors for the ATS platforms that host most company and
staffing-firm openings: Greenhouse, Lever, Ashby, SmartRecruiters.

Each is polled per company "board" (slug), configured via the watchlist.
These endpoints are the public job-board APIs the vendors document for
exactly this purpose."""
from app.connector.http import get_json
from app.connector.spi import (
    ComplianceMode,
    ConnectorConfig,
    ConnectorDescriptor,
    JobQuery,
    RawPosting,
)


def _matches(query: JobQuery, title: str) -> bool:
    if not query.terms:
        return True
    hay = title.lower()
    return any(term.lower() in hay for term in query.terms)


class GreenhouseConnector:
    descriptor = ConnectorDescriptor(
        "greenhouse", "Greenhouse Job Board API",
        ComplianceMode.OFFICIAL_API, rate_limit_per_min=60, supports_auto_apply=True)

    def is_configured(self, cfg: ConnectorConfig) -> bool:
        return bool(cfg.options.get("slug"))

    def search(self, query: JobQuery, cfg: ConnectorConfig) -> list[RawPosting]:
        slug = cfg.options["slug"]
        data = get_json(self.descriptor.id,
                        f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
                        params={"content": "true"}, per_min=cfg.rate_limit_per_min)
        if not isinstance(data, dict):
            return []
        out = []
        for j in data.get("jobs", []):
            if not _matches(query, j.get("title", "")):
                continue
            loc = (j.get("location") or {}).get("name", "")
            out.append(RawPosting(
                connector_id=self.descriptor.id, external_id=str(j.get("id")),
                title=j.get("title", ""), company_name=cfg.options.get("company", slug),
                url=j.get("absolute_url", ""), description_md=j.get("content", "") or "",
                location_text=loc, posted_at=j.get("updated_at"),
                raw={"greenhouse_id": j.get("id")}))
        return out[: query.limit]


class LeverConnector:
    descriptor = ConnectorDescriptor(
        "lever", "Lever Postings API",
        ComplianceMode.OFFICIAL_API, rate_limit_per_min=60, supports_auto_apply=True)

    def is_configured(self, cfg: ConnectorConfig) -> bool:
        return bool(cfg.options.get("slug"))

    def search(self, query: JobQuery, cfg: ConnectorConfig) -> list[RawPosting]:
        slug = cfg.options["slug"]
        data = get_json(self.descriptor.id,
                        f"https://api.lever.co/v0/postings/{slug}",
                        params={"mode": "json"}, per_min=cfg.rate_limit_per_min)
        if not isinstance(data, list):
            return []
        out = []
        for j in data:
            if not _matches(query, j.get("text", "")):
                continue
            cats = j.get("categories") or {}
            out.append(RawPosting(
                connector_id=self.descriptor.id, external_id=j.get("id"),
                title=j.get("text", ""), company_name=cfg.options.get("company", slug),
                url=j.get("hostedUrl", ""),
                description_md=j.get("descriptionPlain", "") or "",
                location_text=cats.get("location", "") or "",
                employment_raw=cats.get("commitment"),
                posted_at=None, raw={"lever_id": j.get("id")}))
        return out[: query.limit]


class AshbyConnector:
    descriptor = ConnectorDescriptor(
        "ashby", "Ashby Posting API",
        ComplianceMode.OFFICIAL_API, rate_limit_per_min=60, supports_auto_apply=True)

    def is_configured(self, cfg: ConnectorConfig) -> bool:
        return bool(cfg.options.get("slug"))

    def search(self, query: JobQuery, cfg: ConnectorConfig) -> list[RawPosting]:
        slug = cfg.options["slug"]
        data = get_json(self.descriptor.id,
                        "https://api.ashbyhq.com/posting-api/job-board/" + slug,
                        params={"includeCompensation": "true"},
                        per_min=cfg.rate_limit_per_min)
        if not isinstance(data, dict):
            return []
        out = []
        for j in data.get("jobs", []):
            if not _matches(query, j.get("title", "")):
                continue
            out.append(RawPosting(
                connector_id=self.descriptor.id, external_id=j.get("id"),
                title=j.get("title", ""), company_name=cfg.options.get("company", slug),
                url=j.get("jobUrl", ""), description_md=j.get("descriptionPlain", "") or "",
                location_text=j.get("location", "") or "",
                is_remote=bool(j.get("isRemote")),
                employment_raw=j.get("employmentType"),
                raw={"ashby_id": j.get("id")}))
        return out[: query.limit]


class SmartRecruitersConnector:
    descriptor = ConnectorDescriptor(
        "smartrecruiters", "SmartRecruiters Posting API",
        ComplianceMode.OFFICIAL_API, rate_limit_per_min=60, supports_auto_apply=False)

    def is_configured(self, cfg: ConnectorConfig) -> bool:
        return bool(cfg.options.get("slug"))

    def search(self, query: JobQuery, cfg: ConnectorConfig) -> list[RawPosting]:
        slug = cfg.options["slug"]
        data = get_json(self.descriptor.id,
                        f"https://api.smartrecruiters.com/v1/companies/{slug}/postings",
                        params={"limit": min(query.limit, 100)},
                        per_min=cfg.rate_limit_per_min)
        if not isinstance(data, dict):
            return []
        out = []
        for j in data.get("content", []):
            if not _matches(query, j.get("name", "")):
                continue
            loc = j.get("location") or {}
            loc_text = ", ".join(x for x in (loc.get("city"), loc.get("region"),
                                             loc.get("country")) if x)
            out.append(RawPosting(
                connector_id=self.descriptor.id, external_id=j.get("id"),
                title=j.get("name", ""), company_name=cfg.options.get("company", slug),
                url=(j.get("ref") or "").replace("api.smartrecruiters.com/v1",
                                                 "jobs.smartrecruiters.com"),
                location_text=loc_text, city=loc.get("city"),
                state=loc.get("region"), country=loc.get("country"),
                is_remote=bool(loc.get("remote")),
                posted_at=j.get("releasedDate"), raw={"sr_id": j.get("id")}))
        return out[: query.limit]
