"""Ingestion pipeline integration test against a real PostgreSQL:
connectors (mocked HTTP) → normalize → dedupe → persist, then verify the
jobs surface through GET /jobs and CSV export."""
import httpx
import respx

from tests.test_auth import auth_headers, register


def _seed_watchlist_and_prefs(user_id: str):
    """Insert a Greenhouse watchlist entry + a company for the user via a
    direct sync session (what the worker uses)."""
    from app.connector.models import Company, CompanyWatchlist
    from app.core.db import worker_session

    with worker_session() as s:
        company = Company(name="Acme", normalized_name="acme")
        s.add(company)
        s.flush()
        s.add(CompanyWatchlist(user_id=user_id, company_id=company.id,
                               connector_id="greenhouse",
                               config={"slug": "acme", "company": "Acme"}))


def test_ingest_for_user_dedupes_and_persists(client):
    pair = register(client).json()
    user_id = pair["user"]["id"]
    _seed_watchlist_and_prefs(user_id)

    # set a preference title so the query matches
    client.put("/api/v1/users/me/preferences",
               json={"desired_titles": ["Java"], "employment_types": ["FULL_TIME"]},
               headers=auth_headers(pair))

    from app.core.db import worker_session
    from app.ingestion.orchestrator import ingest_for_user

    greenhouse_payload = {"jobs": [
        {"id": 10, "title": "Senior Java Developer", "absolute_url": "https://acme.io/10",
         "content": "Java. Sorry, we are unable to sponsor visas.",
         "location": {"name": "Frisco, TX"}, "updated_at": "2026-07-05T00:00:00Z"},
        {"id": 11, "title": "Java Backend Engineer", "absolute_url": "https://acme.io/11",
         "content": "Kafka. H1B sponsorship available.",
         "location": {"name": "Remote"}, "updated_at": "2026-07-06T00:00:00Z"},
    ]}

    with respx.mock:
        respx.get("https://boards-api.greenhouse.io/v1/boards/acme/jobs").mock(
            return_value=httpx.Response(200, json=greenhouse_payload))
        # Dice is a global PUBLIC_FEED connector; return nothing to isolate the test
        respx.get(url__startswith="https://job-search-api.svc.dhigroupinc.com").mock(
            return_value=httpx.Response(200, json={"data": []}))

        with worker_session() as s:
            res1 = ingest_for_user(s, user_id, hours=999, limit=50)
        # second run of the SAME postings must add zero new jobs (dedupe)
        with respx.mock:
            respx.get("https://boards-api.greenhouse.io/v1/boards/acme/jobs").mock(
                return_value=httpx.Response(200, json=greenhouse_payload))
            respx.get(url__startswith="https://job-search-api.svc.dhigroupinc.com").mock(
                return_value=httpx.Response(200, json={"data": []}))
            with worker_session() as s:
                res2 = ingest_for_user(s, user_id, hours=999, limit=50)

    assert res1.jobs_new == 2
    assert "greenhouse" in res1.connectors_run
    assert res2.jobs_new == 0                                    # dedupe held

    # jobs surface through the API with extraction-derived sponsorship
    listed = client.get("/api/v1/jobs?posted_within_hours=100000",
                        headers=auth_headers(pair)).json()
    assert listed["total"] == 2
    titles = {j["title"] for j in listed["items"]}
    assert "Senior Java Developer" in titles

    # CSV export works (the always-available manual path)
    export = client.get("/api/v1/jobs/export?posted_within_hours=100000",
                        headers=auth_headers(pair))
    assert export.status_code == 200
    assert "text/csv" in export.headers["content-type"]
    assert "Senior Java Developer" in export.text


def test_jobs_endpoint_requires_auth(client):
    assert client.get("/api/v1/jobs").status_code == 401
