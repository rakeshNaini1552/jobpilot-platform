"""Scaffold smoke tests: app boots, health works, errors are RFC-7807,
OpenAPI is served, Celery app is wired."""
from fastapi.testclient import TestClient

from app.main import create_app


def client() -> TestClient:
    return TestClient(create_app(), raise_server_exceptions=False)


def test_health_liveness():
    r = client().get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_openapi_served():
    r = client().get("/api/v1/openapi.json")
    assert r.status_code == 200
    body = r.json()
    assert body["info"]["title"] == "JobPilot Platform API"
    assert any(p.startswith("/api/v1/health") for p in body["paths"])


def test_404_is_problem_json():
    r = client().get("/api/v1/nonexistent")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["status"] == 404


def test_celery_beat_schedule():
    from app.worker.celery_app import celery_app
    beat = celery_app.conf.beat_schedule
    assert set(beat) == {"ingest-full-daily", "ingest-incremental",
                         "report-daily", "analytics-weekly"}
    assert celery_app.conf.timezone == "America/Chicago"


def test_secret_crypto_roundtrip():
    from app.core.crypto import decrypt, encrypt, mask
    secret = "sk-verysecretapikey123"
    token = encrypt(secret)
    assert token != secret
    assert decrypt(token) == secret
    m = mask(secret)
    assert "verysecret" not in m and m.startswith("sk-v")
