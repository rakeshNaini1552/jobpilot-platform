"""Phase 11 hardening: the endpoints the coverage audit found missing
(documents, job detail, compliance-gated apply) plus cross-user isolation
and edge cases across the API surface."""
import uuid

from tests.test_auth import auth_headers, register
from tests.test_dashboard import _seed_job, _upload_resume


# ---- documents ---------------------------------------------------------------
def test_generate_document_truthful_and_persisted(client, monkeypatch):
    from app.ai.gateway import AiUnavailable
    monkeypatch.setattr("app.generation.documents.AiGateway.chat",
                        lambda *a, **k: (_ for _ in ()).throw(AiUnavailable("off")))
    pair = register(client).json()
    headers = auth_headers(pair)
    _upload_resume(client, headers)
    job_id = _seed_job()

    r = client.post("/api/v1/documents",
                    json={"job_id": job_id, "doc_type": "COVER_LETTER"},
                    headers=headers)
    assert r.status_code == 201, r.text
    doc = r.json()
    assert "Acme" in doc["content_md"]
    assert doc["model"] is None                    # template fallback path

    listed = client.get(f"/api/v1/documents?job_id={job_id}", headers=headers).json()
    assert len(listed) == 1

    fetched = client.get(f"/api/v1/documents/{doc['id']}", headers=headers)
    assert fetched.status_code == 200


def test_generate_document_requires_resume(client):
    pair = register(client).json()
    job_id = _seed_job()
    r = client.post("/api/v1/documents",
                    json={"job_id": job_id, "doc_type": "COVER_LETTER"},
                    headers=auth_headers(pair))
    assert r.status_code == 409
    assert "resume" in r.json()["detail"].lower()


# ---- job detail ----------------------------------------------------------------
def test_job_detail_includes_extraction_match_and_tracking(client):
    pair = register(client).json()
    headers = auth_headers(pair)
    _upload_resume(client, headers)
    job_id = _seed_job()

    from app.core.db import worker_session
    from app.matching.api import score_jobs_for_user
    with worker_session() as s:
        score_jobs_for_user(s, uuid.UUID(pair["user"]["id"]))
    app_id = client.post("/api/v1/applications", json={"job_id": job_id},
                         headers=headers).json()["id"]

    detail = client.get(f"/api/v1/jobs/{job_id}", headers=headers).json()
    assert detail["title"] == "Senior Java Developer"
    assert detail["company"]["name"] == "Acme"
    assert "Java" in detail["extraction"]["skills"]
    assert detail["extraction"]["sponsorship"] == "SPONSOR_FRIENDLY"
    assert detail["match"]["overall"] > 50
    assert detail["application_id"] == app_id

    assert client.get(f"/api/v1/jobs/{uuid.uuid4()}",
                      headers=headers).status_code == 404
    assert client.get("/api/v1/jobs/not-a-uuid",
                      headers=headers).status_code == 404


# ---- compliance-gated apply -----------------------------------------------------
def test_auto_apply_gated_by_compliance_mode(client):
    pair = register(client).json()
    headers = auth_headers(pair)
    job_id = _seed_job()                            # connector_id='dice' (PUBLIC_FEED)
    app_id = client.post("/api/v1/applications", json={"job_id": job_id},
                         headers=headers).json()["id"]

    r = client.post(f"/api/v1/applications/{app_id}/apply", headers=headers)
    assert r.status_code == 409                     # dice may never auto-apply
    body = r.json()
    assert body["type"].endswith("automation-not-permitted")
    assert body["apply_url"].startswith("https://")  # manual path always offered

    # the gating decision is auditable
    from sqlalchemy import text

    from app.core.db import worker_session
    with worker_session() as s:
        row = s.execute(text(
            "SELECT detail FROM audit_events WHERE event_type='tracker.apply_gated' "
            "ORDER BY id DESC LIMIT 1")).one()
        assert row.detail["connector"] == "dice"


def test_auto_apply_permitted_source_is_honest_501(client):
    pair = register(client).json()
    headers = auth_headers(pair)
    job_id = _seed_job(url="https://boards.greenhouse.io/acme/jobs/1")
    # flip the seeded job to a connector that permits automation
    from sqlalchemy import text

    from app.core.db import worker_session
    with worker_session() as s:
        s.execute(text("UPDATE jobs SET connector_id='greenhouse' WHERE id=:i"),
                  {"i": job_id})
    app_id = client.post("/api/v1/applications", json={"job_id": job_id},
                         headers=headers).json()["id"]
    r = client.post(f"/api/v1/applications/{app_id}/apply", headers=headers)
    assert r.status_code == 501                     # permitted but not faked
    assert "apply_url" in r.json()


# ---- cross-user isolation --------------------------------------------------------
def test_applications_and_documents_are_user_isolated(client, monkeypatch):
    from app.ai.gateway import AiUnavailable
    monkeypatch.setattr("app.generation.documents.AiGateway.chat",
                        lambda *a, **k: (_ for _ in ()).throw(AiUnavailable("off")))
    owner = register(client).json()
    oh = auth_headers(owner)
    _upload_resume(client, oh)
    job_id = _seed_job()
    app_id = client.post("/api/v1/applications", json={"job_id": job_id},
                         headers=oh).json()["id"]
    doc_id = client.post("/api/v1/documents",
                         json={"job_id": job_id, "doc_type": "LINKEDIN_MESSAGE"},
                         headers=oh).json()["id"]

    other = register(client, email="intruder@example.com").json()
    ih = auth_headers(other)
    assert client.get(f"/api/v1/applications/{app_id}", headers=ih).status_code == 404
    assert client.get(f"/api/v1/documents/{doc_id}", headers=ih).status_code == 404
    assert client.post(f"/api/v1/applications/{app_id}/status",
                       json={"to_status": "APPLIED"}, headers=ih).status_code == 404
    assert client.get("/api/v1/applications", headers=ih).json()["total"] == 0
    assert client.get("/api/v1/documents", headers=ih).json() == []


def test_resumes_are_user_isolated(client):
    owner = register(client).json()
    resume = _upload_resume(client, auth_headers(owner))
    other = register(client, email="intruder@example.com").json()
    r = client.get(f"/api/v1/resumes/{resume['id']}", headers=auth_headers(other))
    assert r.status_code == 404
    assert client.get("/api/v1/resumes", headers=auth_headers(other)).json() == []


# ---- edge cases -------------------------------------------------------------------
def test_pagination_bounds_enforced(client):
    pair = register(client).json()
    headers = auth_headers(pair)
    assert client.get("/api/v1/jobs?size=101", headers=headers).status_code == 422
    assert client.get("/api/v1/jobs?page=0", headers=headers).status_code == 422


def test_invalid_status_transition_value_rejected(client):
    pair = register(client).json()
    headers = auth_headers(pair)
    job_id = _seed_job()
    app_id = client.post("/api/v1/applications", json={"job_id": job_id},
                         headers=headers).json()["id"]
    r = client.post(f"/api/v1/applications/{app_id}/status",
                    json={"to_status": "GHOSTED"}, headers=headers)
    assert r.status_code == 422                     # closed vocabulary enforced


def test_status_change_is_idempotent_no_duplicate_events(client):
    pair = register(client).json()
    headers = auth_headers(pair)
    job_id = _seed_job()
    app_id = client.post("/api/v1/applications", json={"job_id": job_id},
                         headers=headers).json()["id"]
    for _ in range(3):                              # same status thrice
        client.post(f"/api/v1/applications/{app_id}/status",
                    json={"to_status": "SAVED"}, headers=headers)
    events = client.get(f"/api/v1/applications/{app_id}/events",
                        headers=headers).json()
    assert len(events) == 1                         # only the creation event
