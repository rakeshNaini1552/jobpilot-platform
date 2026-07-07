"""Connector unit tests — mocked HTTP (respx), plus normalize/dedupe logic.
No network, deterministic."""
import httpx
import respx

from app.connector.connectors.ats import GreenhouseConnector, LeverConnector
from app.connector.connectors.dice import DiceConnector
from app.connector.connectors.search_links import LinkedInLinks
from app.connector.spi import ComplianceMode, ConnectorConfig, JobQuery
from app.ingestion.normalize import (
    classify_seniority,
    classify_sponsorship,
    dedupe_hash,
    normalize_company_name,
)


def test_compliance_modes_are_declared():
    assert GreenhouseConnector().descriptor.compliance_mode == ComplianceMode.OFFICIAL_API
    assert DiceConnector().descriptor.compliance_mode == ComplianceMode.PUBLIC_FEED
    assert LinkedInLinks().descriptor.compliance_mode == ComplianceMode.SEARCH_LINK
    # Only official/automation connectors may auto-apply
    assert GreenhouseConnector().descriptor.supports_auto_apply is True
    assert DiceConnector().descriptor.supports_auto_apply is False


@respx.mock
def test_greenhouse_search_parses_and_filters():
    respx.get("https://boards-api.greenhouse.io/v1/boards/acme/jobs").mock(
        return_value=httpx.Response(200, json={"jobs": [
            {"id": 1, "title": "Senior Java Developer", "absolute_url": "https://acme.io/1",
             "content": "Java Spring", "location": {"name": "Remote, US"},
             "updated_at": "2026-07-01T00:00:00Z"},
            {"id": 2, "title": "Product Manager", "absolute_url": "https://acme.io/2",
             "content": "roadmaps", "location": {"name": "NYC"}},
        ]}))
    cfg = ConnectorConfig(options={"slug": "acme", "company": "Acme"})
    postings = GreenhouseConnector().search(JobQuery(terms=["Java"]), cfg)
    assert len(postings) == 1
    p = postings[0]
    assert p.title == "Senior Java Developer"
    assert p.company_name == "Acme"
    assert p.external_id == "1"


@respx.mock
def test_lever_search_parses():
    respx.get("https://api.lever.co/v0/postings/acme").mock(
        return_value=httpx.Response(200, json=[
            {"id": "abc", "text": "Backend Engineer", "hostedUrl": "https://jobs.lever.co/acme/abc",
             "descriptionPlain": "Go and Kafka",
             "categories": {"location": "Austin, TX", "commitment": "Full-time"}},
        ]))
    cfg = ConnectorConfig(options={"slug": "acme"})
    postings = LeverConnector().search(JobQuery(terms=["Backend"]), cfg)
    assert postings[0].url == "https://jobs.lever.co/acme/abc"
    assert postings[0].employment_raw == "Full-time"


@respx.mock
def test_connector_http_failure_is_swallowed():
    respx.get("https://boards-api.greenhouse.io/v1/boards/acme/jobs").mock(
        return_value=httpx.Response(500))
    cfg = ConnectorConfig(options={"slug": "acme"})
    assert GreenhouseConnector().search(JobQuery(), cfg) == []   # never raises


def test_search_link_builds_compliant_url_and_never_scrapes():
    urls = LinkedInLinks().build_urls(
        JobQuery(terms=["Java Developer"], location="Dallas, TX",
                 posted_within_hours=24), ConnectorConfig())
    assert len(urls) == 1
    assert urls[0]["url"].startswith("https://www.linkedin.com/jobs/search/")
    assert "keywords=Java+Developer" in urls[0]["url"]
    assert "f_TPR=r86400" in urls[0]["url"]                      # last 24h


# ---- normalize / dedupe --------------------------------------------------
def test_company_normalization_collapses_suffixes():
    assert normalize_company_name("Acme Inc.") == normalize_company_name("ACME LLC")
    assert normalize_company_name("Tata Consultancy Services Limited") == \
        normalize_company_name("Tata Consultancy Services")


def test_dedupe_hash_uses_canonical_url():
    from app.connector.spi import RawPosting
    a = RawPosting("dice", "Dev", "Acme", "https://x.co/1?utm=abc")
    b = RawPosting("greenhouse", "Dev", "Acme", "https://x.co/1#section")
    assert dedupe_hash(a) == dedupe_hash(b)                      # same job, diff source


def test_sponsorship_and_seniority_classification():
    assert classify_sponsorship("We are unable to sponsor visas") == "NO_SPONSOR"
    assert classify_sponsorship("H1B sponsorship available") == "SPONSOR_FRIENDLY"
    assert classify_sponsorship("great team") == "UNKNOWN"
    assert classify_seniority("Senior Software Engineer", "") == "SENIOR"
    assert classify_seniority("Software Engineer", "") == "MID"
    assert classify_seniority("Principal Architect", "") == "PRINCIPAL"
