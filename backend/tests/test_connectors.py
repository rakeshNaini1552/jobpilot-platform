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


# ---- arrangement classification: negation + source field priority -------------
def test_c2c_negations_do_not_classify_as_c2c():
    from app.connector.spi import guess_arrangement
    # postings that MENTION C2C to refuse it
    assert guess_arrangement("W2 only. No C2C or third party agencies.") == "W2"
    assert guess_arrangement("Cannot work with corp-to-corp candidates") == "W2"
    assert guess_arrangement("C2C not accepted, W2 basis") == "W2"
    assert guess_arrangement("No third-party candidates please") == "W2"
    # genuine C2C still detected
    assert guess_arrangement("Open to C2C and W2") == "C2C"
    assert guess_arrangement("corp to corp welcome") == "C2C"
    assert guess_arrangement("1099 contract") == "C1099"
    assert guess_arrangement("nothing about arrangements") == "UNSPECIFIED"


def test_source_employment_field_is_authoritative():
    from app.connector.spi import guess_arrangement
    # Dice-style employmentType beats free text
    assert guess_arrangement("No C2C in the text",
                             employment_raw="Contract Corp-To-Corp") == "C2C"
    assert guess_arrangement("C2C mentioned in text",
                             employment_raw="Contract W2") == "W2"
    assert guess_arrangement("", employment_raw="Contract Independent") == "C1099"


# ---- new keyless public feeds ---------------------------------------------------
@respx.mock
def test_remoteok_parses_and_skips_legal_notice():
    from app.connector.connectors.public_feeds import RemoteOKConnector
    respx.get("https://remoteok.com/api").mock(return_value=httpx.Response(200, json=[
        {"legal": "you must link back"},                     # notice element
        {"id": 7, "position": "Senior Java Engineer", "company": "Acme Remote",
         "url": "https://remoteok.com/jobs/7", "description": "<p>Java & AWS</p>",
         "location": "USA", "salary_min": 120000, "salary_max": 150000,
         "date": "2026-07-10T00:00:00+00:00", "tags": ["java"]},
    ]))
    posts = RemoteOKConnector().search(JobQuery(terms=["Java"]), ConnectorConfig())
    assert len(posts) == 1
    assert posts[0].title == "Senior Java Engineer"
    assert posts[0].is_remote is True
    assert "<p>" not in posts[0].description_md              # html stripped


@respx.mock
def test_remotive_parses():
    from app.connector.connectors.public_feeds import RemotiveConnector
    respx.get("https://remotive.com/api/remote-jobs").mock(
        return_value=httpx.Response(200, json={"jobs": [
            {"id": 3, "title": "Java Backend Developer", "company_name": "Remotive Co",
             "url": "https://remotive.com/j/3", "description": "<b>Spring Boot</b>",
             "candidate_required_location": "USA only", "job_type": "full_time",
             "publication_date": "2026-07-12T08:00:00"},
        ]}))
    posts = RemotiveConnector().search(JobQuery(terms=["Java"]), ConnectorConfig())
    assert posts[0].company_name == "Remotive Co"
    assert posts[0].location_text == "USA only"


def test_remote_matching_is_word_bounded():
    """'Java Developer' must not match 'javascript' tags."""
    from app.connector.connectors.public_feeds import _matches
    q = JobQuery(terms=["Java Developer"])
    assert _matches(q, "Frontend Dev", extra="javascript react") is False
    assert _matches(q, "Backend Engineer (Java)") is True
    assert _matches(q, "Platform Engineer", extra="java spring") is True
