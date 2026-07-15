"""Phase 10 tests: notification settings, daily report build + delivery
bookkeeping, weekly snapshots, run recording, and the admin panel."""
import uuid

from tests.test_auth import auth_headers, register
from tests.test_dashboard import _seed_job, _upload_resume


# ---- notification settings -------------------------------------------------
def test_notification_settings_roundtrip_and_webhook_masking(client):
    pair = register(client).json()
    headers = auth_headers(pair)

    got = client.get("/api/v1/users/me/notification-settings", headers=headers)
    assert got.status_code == 200
    assert got.json()["email_enabled"] is True
    assert got.json()["daily_report_hour"] == 21

    put = client.put("/api/v1/users/me/notification-settings", headers=headers,
                     json={"email_enabled": False, "daily_report_hour": 8,
                           "slack_webhook": "https://hooks.slack.com/services/T/B/secret"})
    assert put.status_code == 200
    body = put.json()
    assert body["email_enabled"] is False
    assert "secret" not in (body["slack_webhook"] or "")     # write-only, masked

    # masked value back in a PUT must NOT clobber the stored webhook
    client.put("/api/v1/users/me/notification-settings", headers=headers,
               json={"email_enabled": False, "daily_report_hour": 8,
                     "slack_webhook": body["slack_webhook"]})
    from app.core.crypto import decrypt
    from app.core.db import worker_session
    from app.notification.models import NotificationSettings
    with worker_session() as s:
        row = s.get(NotificationSettings, uuid.UUID(pair["user"]["id"]))
        assert decrypt(row.slack_webhook_enc).endswith("/secret")


# ---- daily report -----------------------------------------------------------
def test_daily_report_builds_from_real_data(client):
    pair = register(client).json()
    headers = auth_headers(pair)
    _upload_resume(client, headers)
    job_id = _seed_job()

    from app.core.db import worker_session
    from app.matching.service import score_jobs_for_user
    from app.notification.report import build_daily_report
    from app.user.models import User
    with worker_session() as s:
        uid = uuid.UUID(pair["user"]["id"])
        score_jobs_for_user(s, uid)
        report = build_daily_report(s, s.get(User, uid))

    assert "1 new matches" in report["subject"]
    assert "Senior Java Developer" in report["html"]
    assert "Acme" in report["html"]
    assert report["payload"]["kpis"][0]["value"] == 1
    assert report["payload"]["actions"]                       # suggests reviewing it
    assert job_id  # silence unused warning


def test_daily_report_task_records_run_and_skips_without_smtp(client):
    pair = register(client).json()

    from app.core.db import worker_session
    from app.notification.tasks import send_daily_reports
    totals = send_daily_reports.run()
    assert totals == {"sent": 0, "skipped": 1, "failed": 0}   # no SMTP configured

    from sqlalchemy import text
    with worker_session() as s:
        run = s.execute(text(
            "SELECT status, stats FROM scheduled_runs WHERE task_key='report.daily' "
            "ORDER BY id DESC LIMIT 1")).one()
        assert run.status == "SUCCESS"
        note = s.execute(text(
            "SELECT channel, status, error FROM notifications "
            "WHERE user_id = :u"), {"u": pair["user"]["id"]}).one()
        assert (note.channel, note.status) == ("EMAIL", "SKIPPED")
        assert "SMTP" in note.error


def test_email_channel_sends_when_configured(client, monkeypatch):
    """SMTP wire-level check with a stubbed smtplib."""
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            sent["host"], sent["port"] = host, port
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def login(self, user, password): sent["login"] = (user, password)
        def send_message(self, msg):
            sent["to"], sent["subject"] = msg["To"], msg["Subject"]

    import smtplib
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP)
    from app.core.settings import get_settings
    s = get_settings()
    monkeypatch.setattr(s, "smtp_host", "smtp.gmail.com")
    monkeypatch.setattr(s, "smtp_user", "rakesh@example.com")
    monkeypatch.setattr(s, "smtp_password", "app-password")

    from app.notification.channels import send_email
    ok, err = send_email("rakesh@example.com", "Test report", "<b>hi</b>")
    assert ok and err is None
    assert sent["port"] == 465 and sent["to"] == "rakesh@example.com"


def test_webhook_channel(client):
    import httpx
    import respx

    from app.notification.channels import send_webhook
    with respx.mock:
        respx.post("https://hooks.slack.com/services/T/B/x").mock(
            return_value=httpx.Response(200))
        ok, err = send_webhook("https://hooks.slack.com/services/T/B/x", "hello")
    assert ok and err is None


# ---- weekly analytics snapshot ----------------------------------------------
def test_weekly_analytics_writes_snapshot(client):
    pair = register(client).json()
    from app.analytics.tasks import run_weekly_analytics
    totals = run_weekly_analytics.run()
    assert totals["users"] == 1

    from sqlalchemy import text

    from app.core.db import worker_session
    with worker_session() as s:
        row = s.execute(text(
            "SELECT metrics FROM analytics_snapshots WHERE user_id = :u"),
            {"u": pair["user"]["id"]}).one()
        assert "funnel" in row.metrics
    # idempotent same-day rerun (upsert, not violation)
    assert run_weekly_analytics.run()["users"] == 1


# ---- ad-hoc run keys don't violate the FK -----------------------------------
def test_record_run_auto_registers_adhoc_key(client):
    from sqlalchemy import text

    from app.core.db import worker_session
    from app.scheduler.api import finish_run, record_run
    with worker_session() as s:
        run_id = record_run(s, "ingest.ondemand")
        finish_run(s, run_id, "SUCCESS", {"jobs_new": 3})
    with worker_session() as s:
        row = s.execute(text(
            "SELECT enabled FROM scheduled_tasks WHERE key='ingest.ondemand'")).one()
        assert row.enabled is False                            # registered, not scheduled


# ---- admin panel --------------------------------------------------------------
def test_admin_schedules_and_runs(client):
    admin = register(client).json()                            # first user = ADMIN
    headers = auth_headers(admin)

    schedules = client.get("/api/v1/admin/schedules", headers=headers).json()
    assert {s["key"] for s in schedules} >= {
        "ingest.full", "ingest.incremental", "report.daily", "analytics.weekly"}

    patched = client.patch("/api/v1/admin/schedules/report.daily",
                           json={"cron": "0 20 * * *"}, headers=headers)
    assert patched.status_code == 200
    assert patched.json()["cron"] == "0 20 * * *"

    bad = client.patch("/api/v1/admin/schedules/report.daily",
                       json={"cron": "not-a-cron"}, headers=headers)
    assert bad.status_code == 422

    from app.analytics.tasks import run_weekly_analytics
    run_weekly_analytics.run()
    runs = client.get("/api/v1/admin/runs?task_key=analytics.weekly",
                      headers=headers).json()
    assert runs and runs[0]["status"] == "SUCCESS"

    # restore the seed cron (scheduled_tasks persists across tests)
    client.patch("/api/v1/admin/schedules/report.daily",
                 json={"cron": "0 21 * * *"}, headers=headers)


def test_admin_connectors_toggle(client):
    admin = register(client).json()
    headers = auth_headers(admin)

    connectors = client.get("/api/v1/admin/connectors", headers=headers).json()
    assert any(c["connector_id"] == "dice" for c in connectors)

    r = client.patch("/api/v1/admin/connectors/dice",
                     json={"enabled": False, "rate_limit_per_min": 5},
                     headers=headers)
    assert r.status_code == 200
    assert r.json()["enabled"] is False

    # restore for other tests (seed table persists across tests)
    client.patch("/api/v1/admin/connectors/dice",
                 json={"enabled": True, "rate_limit_per_min": 20}, headers=headers)


def test_admin_requires_admin_role(client):
    register(client)                                           # first = ADMIN
    user = register(client, email="pleb@example.com").json()   # second = USER
    r = client.get("/api/v1/admin/schedules", headers=auth_headers(user))
    assert r.status_code == 403


# ---- ingestion celery tasks end-to-end ----------------------------------------
def test_ingestion_task_records_run_and_scores(client):
    """Full worker path: task → connectors (mocked) → dedupe → score → run row."""
    import httpx
    import respx

    from tests.test_auth import auth_headers  # noqa: F401

    pair = register(client).json()
    headers = auth_headers(pair)
    _upload_resume(client, headers)
    client.put("/api/v1/users/me/preferences",
               json={"desired_titles": ["Java"], "employment_types": ["FULL_TIME"]},
               headers=headers)

    from app.ingestion.tasks import run_ingestion_for_user

    with respx.mock:
        respx.get(url__startswith="https://job-search-api.svc.dhigroupinc.com").mock(
            return_value=httpx.Response(200, json={"data": [{
                "id": 991, "title": "Java Platform Engineer",
                "companyName": "Acme", "detailsPageUrl": "https://dice.com/j/991",
                "summary": "Java and AWS.", "postedDate": "2026-07-14T00:00:00Z",
                "jobLocation": {"displayName": "Remote"}, "isRemote": True,
                "employmentType": "Full-time"}]}))
        stats = run_ingestion_for_user.run(pair["user"]["id"])

    assert stats["jobs_new"] == 1
    assert stats["scored"] == 1

    from sqlalchemy import text

    from app.core.db import worker_session
    with worker_session() as s:
        run = s.execute(text(
            "SELECT status, stats FROM scheduled_runs "
            "WHERE task_key='ingest.ondemand' ORDER BY id DESC LIMIT 1")).one()
        assert run.status == "SUCCESS"
        assert run.stats["jobs_new"] == 1
