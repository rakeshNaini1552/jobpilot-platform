"""Dice PUBLIC_FEED connector — Dice's own public search API (the endpoint
its website frontend calls). Ported from the validated prototype."""
from app.connector.http import get_json
from app.connector.spi import (
    ComplianceMode,
    ConnectorConfig,
    ConnectorDescriptor,
    JobQuery,
    RawPosting,
)

SEARCH_URL = "https://job-search-api.svc.dhigroupinc.com/v1/dice/jobs/search"
PUBLIC_API_KEY = "1YAt0R9wBg4WfsF9VB2778F5CHLAPMVW3WAZcKd8"  # embedded in dice.com frontend


class DiceConnector:
    descriptor = ConnectorDescriptor(
        "dice", "Dice public search feed",
        ComplianceMode.PUBLIC_FEED, rate_limit_per_min=20, supports_auto_apply=False)

    def is_configured(self, cfg: ConnectorConfig) -> bool:
        return True  # public endpoint, no per-source config required

    def search(self, query: JobQuery, cfg: ConnectorConfig) -> list[RawPosting]:
        term = " ".join(query.terms) or "software engineer"
        params = {
            "q": term, "countryCode2": "US", "radius": "30", "radiusUnit": "mi",
            "page": "1", "pageSize": str(min(query.limit, 100)),
            "fields": ("id|jobId|title|companyName|detailsPageUrl|postedDate|"
                       "jobLocation.displayName|employmentType|summary|isRemote"),
            "interactionType": "0", "fj": "false", "includeRemote": "true",
        }
        if query.location:
            params["location"] = query.location
        if query.posted_within_hours <= 24:
            params["filters.postedDate"] = "ONE"
        elif query.posted_within_hours <= 24 * 7:
            params["filters.postedDate"] = "SEVEN"

        data = get_json(self.descriptor.id, SEARCH_URL, params=params,
                        per_min=cfg.rate_limit_per_min,
                        headers={"x-api-key": PUBLIC_API_KEY})
        if not isinstance(data, dict):
            return []
        out = []
        for d in data.get("data", []):
            out.append(RawPosting(
                connector_id=self.descriptor.id, external_id=str(d.get("id")),
                title=d.get("title", ""), company_name=d.get("companyName", ""),
                url=d.get("detailsPageUrl", ""), description_md=d.get("summary", "") or "",
                location_text=(d.get("jobLocation") or {}).get("displayName", ""),
                is_remote=bool(d.get("isRemote")),
                employment_raw=d.get("employmentType"),
                posted_at=d.get("postedDate"), raw={"dice_id": d.get("id")}))
        return out[: query.limit]
