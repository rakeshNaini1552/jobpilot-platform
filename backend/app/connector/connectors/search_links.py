"""SEARCH_LINK connectors — LinkedIn, Indeed, Monster, ZipRecruiter.

We do NOT scrape these. We build compliant search URLs the user opens
themselves; matched jobs are exported for manual application. This is the
ToS-safe way to cover boards that prohibit automated access."""
from urllib.parse import urlencode

from app.connector.spi import ComplianceMode, ConnectorConfig, ConnectorDescriptor, JobQuery


class _SearchLinkBase:
    descriptor: ConnectorDescriptor
    base: str

    def is_configured(self, cfg: ConnectorConfig) -> bool:
        return True

    def _params(self, query: JobQuery) -> dict:
        raise NotImplementedError

    def build_urls(self, query: JobQuery, cfg: ConnectorConfig) -> list[dict]:
        urls = []
        for term in (query.terms or ["software engineer"]):
            params = self._params(query)
            params[self._term_key] = term
            urls.append({"term": term, "board": self.descriptor.id,
                         "url": f"{self.base}?{urlencode(params)}"})
        return urls


class LinkedInLinks(_SearchLinkBase):
    descriptor = ConnectorDescriptor("linkedin_links", "LinkedIn search links",
                                     ComplianceMode.SEARCH_LINK, rate_limit_per_min=0)
    base = "https://www.linkedin.com/jobs/search/"
    _term_key = "keywords"

    def _params(self, query: JobQuery) -> dict:
        p: dict = {"location": query.location or "United States"}
        if query.posted_within_hours:
            p["f_TPR"] = f"r{query.posted_within_hours * 3600}"
        if query.remote:
            p["f_WT"] = "2"
        return p


class IndeedLinks(_SearchLinkBase):
    descriptor = ConnectorDescriptor("indeed_links", "Indeed search links",
                                     ComplianceMode.SEARCH_LINK, rate_limit_per_min=0)
    base = "https://www.indeed.com/jobs"
    _term_key = "q"

    def _params(self, query: JobQuery) -> dict:
        p: dict = {"l": query.location or ""}
        if query.posted_within_hours:
            p["fromage"] = max(1, query.posted_within_hours // 24)
        return p


class MonsterLinks(_SearchLinkBase):
    descriptor = ConnectorDescriptor("monster_links", "Monster search links",
                                     ComplianceMode.SEARCH_LINK, rate_limit_per_min=0)
    base = "https://www.monster.com/jobs/search"
    _term_key = "q"

    def _params(self, query: JobQuery) -> dict:
        return {"where": query.location or ""}


class ZipRecruiterLinks(_SearchLinkBase):
    descriptor = ConnectorDescriptor("zip_links", "ZipRecruiter search links",
                                     ComplianceMode.SEARCH_LINK, rate_limit_per_min=0)
    base = "https://www.ziprecruiter.com/jobs-search"
    _term_key = "search"

    def _params(self, query: JobQuery) -> dict:
        p: dict = {"location": query.location or ""}
        if query.posted_within_hours:
            p["days"] = max(1, query.posted_within_hours // 24)
        return p
