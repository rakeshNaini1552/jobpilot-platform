"""OFFICIAL_API aggregators with free tiers: Adzuna and Jooble. These index
Indeed / Monster / ZipRecruiter inventory indirectly and are the compliant
way to reach those boards. Both require free API credentials, stored
(encrypted) in connector_settings.config."""
from app.connector.http import get_json
from app.connector.spi import (
    ComplianceMode,
    ConnectorConfig,
    ConnectorDescriptor,
    JobQuery,
    RawPosting,
)

COUNTRY_TLD = {"US": "us", "GB": "gb", "CA": "ca", "IN": "in",
               "AU": "au", "DE": "de"}


class AdzunaConnector:
    descriptor = ConnectorDescriptor(
        "adzuna", "Adzuna API",
        ComplianceMode.OFFICIAL_API, rate_limit_per_min=25, supports_auto_apply=False)

    def is_configured(self, cfg: ConnectorConfig) -> bool:
        return bool(cfg.options.get("app_id") and cfg.options.get("app_key"))

    def search(self, query: JobQuery, cfg: ConnectorConfig) -> list[RawPosting]:
        country = COUNTRY_TLD.get(query.country.upper(), "us")
        params = {
            "app_id": cfg.options["app_id"], "app_key": cfg.options["app_key"],
            "what": " ".join(query.terms) or "software engineer",
            "results_per_page": min(query.limit, 50),
            "max_days_old": max(1, query.posted_within_hours // 24),
            "content-type": "application/json",
        }
        if query.location:
            params["where"] = query.location
        data = get_json(self.descriptor.id,
                        f"https://api.adzuna.com/v1/api/jobs/{country}/search/1",
                        params=params, per_min=cfg.rate_limit_per_min)
        if not isinstance(data, dict):
            return []
        out = []
        for j in data.get("results", []):
            out.append(RawPosting(
                connector_id=self.descriptor.id, external_id=str(j.get("id")),
                title=j.get("title", ""),
                company_name=(j.get("company") or {}).get("display_name", ""),
                url=j.get("redirect_url", ""), description_md=j.get("description", "") or "",
                location_text=(j.get("location") or {}).get("display_name", ""),
                salary_min=int(j["salary_min"]) if j.get("salary_min") else None,
                salary_max=int(j["salary_max"]) if j.get("salary_max") else None,
                salary_currency="USD" if country == "us" else None,
                salary_period="yearly",
                employment_raw=j.get("contract_time"),
                posted_at=j.get("created"), raw={"adzuna_id": j.get("id")}))
        return out[: query.limit]


class JoobleConnector:
    descriptor = ConnectorDescriptor(
        "jooble", "Jooble API",
        ComplianceMode.OFFICIAL_API, rate_limit_per_min=25, supports_auto_apply=False)

    def is_configured(self, cfg: ConnectorConfig) -> bool:
        return bool(cfg.options.get("api_key"))

    def search(self, query: JobQuery, cfg: ConnectorConfig) -> list[RawPosting]:
        import httpx

        from app.connector.http import USER_AGENT
        body = {"keywords": " ".join(query.terms) or "software engineer",
                "location": query.location or "", "page": "1"}
        try:
            r = httpx.post(f"https://jooble.org/api/{cfg.options['api_key']}",
                           json=body, timeout=30,
                           headers={"User-Agent": USER_AGENT})
            r.raise_for_status()
            data = r.json()
        except Exception:
            return []
        out = []
        for j in data.get("jobs", [])[: query.limit]:
            out.append(RawPosting(
                connector_id=self.descriptor.id, external_id=str(j.get("id")),
                title=j.get("title", ""), company_name=j.get("company", ""),
                url=j.get("link", ""), description_md=j.get("snippet", "") or "",
                location_text=j.get("location", ""), employment_raw=j.get("type"),
                posted_at=j.get("updated"), raw={"jooble_id": j.get("id")}))
        return out
