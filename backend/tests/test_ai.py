"""AI layer tests — gateway fallback, extraction, matching math, the
truthfulness guardrail, document generation, and the assistant. All run with
NO AI provider configured, proving graceful degradation."""
import pytest

from app.ai.extraction import Extraction, extract
from app.ai.gateway import AiGateway, AiUnavailable
from app.generation.documents import generate
from app.generation.guardrail import check_generated
from app.matching.engine import MatchInput, add_reasoning, score


# ---- gateway fallback -----------------------------------------------------
def test_gateway_unavailable_when_no_providers(monkeypatch):
    from app.core.settings import get_settings
    s = get_settings()
    monkeypatch.setattr(s, "ollama_base_url", "http://127.0.0.1:1")   # unreachable
    monkeypatch.setattr(s, "openrouter_api_key", "")
    monkeypatch.setattr(s, "gemini_api_key", "")
    monkeypatch.setattr(s, "anthropic_api_key", "")
    monkeypatch.setattr(s, "openai_api_key", "")
    gw = AiGateway()
    with pytest.raises(AiUnavailable):
        gw.chat([{"role": "user", "content": "hi"}], max_tokens=1)
    assert gw.available() is False


# ---- extraction (heuristic fallback) --------------------------------------
def test_extract_heuristic_without_ai(monkeypatch):
    monkeypatch.setattr("app.ai.extraction.AiGateway.chat_json",
                        lambda *a, **k: (_ for _ in ()).throw(AiUnavailable("no ai")))
    jd = ("We need Python, AWS, Kafka and PostgreSQL. Senior role. "
          "Sorry, we are unable to sponsor visas. Recruiter: Jane Doe jane@acme.com")
    ext = extract("Senior Backend Engineer", jd)
    assert ext.method == "HEURISTIC"
    assert "Python" in ext.skills and "Kafka" in ext.skills
    assert ext.sponsorship == "NO_SPONSOR"
    assert ext.seniority == "SENIOR"
    assert ext.recruiter_contact == "jane@acme.com"


# ---- matching math --------------------------------------------------------
def _mk_input(**over):
    base = dict(
        job_title="Senior Java Developer", job_workplace="REMOTE",
        job_salary_min=120000, job_salary_max=160000,
        extraction=Extraction(skills=["Java", "AWS", "Kafka", "SQL"],
                              sponsorship="SPONSOR_FRIENDLY"),
        resume_skills=["Java", "AWS", "SQL", "Spring Boot"],
        resume_text="Experienced in Java, AWS, SQL and Spring Boot.",
        pref_salary_min=130000, pref_workplace=["REMOTE"], needs_sponsorship=False)
    base.update(over)
    return MatchInput(**base)


def test_score_computes_all_subscores_and_gap():
    r = score(_mk_input())
    # 3 of 4 required skills present → 75%
    assert r.resume_pct == 75.0
    assert r.salary_score == 100.0          # top (160k) >= pref (130k)
    assert r.location_score == 100.0        # REMOTE ∈ prefs
    assert r.visa_score == 100.0            # no sponsorship need
    assert 0 <= r.overall <= 100
    missing = [g["skill"] for g in r.skill_gap if not g["have"]]
    assert missing == ["Kafka"]


def test_visa_penalty_when_sponsorship_needed_but_none():
    r = score(_mk_input(
        extraction=Extraction(skills=["Java"], sponsorship="NO_SPONSOR"),
        needs_sponsorship=True))
    assert r.visa_score == 0.0


def test_salary_partial_when_below_expectation():
    r = score(_mk_input(job_salary_min=60000, job_salary_max=60000,
                        pref_salary_min=120000))
    assert r.salary_score == 50.0           # 100 * 60/120


def test_add_reasoning_degrades_without_ai(monkeypatch):
    monkeypatch.setattr("app.ai.gateway.AiGateway.chat",
                        lambda *a, **k: (_ for _ in ()).throw(AiUnavailable("no ai")))
    r = add_reasoning(score(_mk_input()), _mk_input())
    assert "Kafka" in r.reasoning and r.model is None


# ---- guardrail ------------------------------------------------------------
def test_guardrail_flags_fabricated_skill():
    source = "Backend engineer skilled in Python and AWS."
    good = "Python and AWS specialist ready to contribute."
    bad = "Expert in Python, AWS, and Kubernetes with a PhD."
    assert check_generated(source, good).ok is True
    report = check_generated(source, bad)
    assert report.ok is False
    assert "kubernetes" in report.fabricated_skills
    assert any("phd" in c for c in report.fabricated_credentials)


# ---- document generation --------------------------------------------------
def test_generate_falls_back_to_truthful_template(monkeypatch):
    monkeypatch.setattr("app.generation.documents.AiGateway.chat",
                        lambda *a, **k: (_ for _ in ()).throw(AiUnavailable("no ai")))
    doc = generate("COVER_LETTER", candidate_name="Rakesh Naini",
                   resume_text="Java, AWS and SQL developer.",
                   overlap_skills=["Java", "AWS"], job_title="Backend Engineer",
                   job_company="Acme", job_description="Java and AWS role.")
    assert doc.model is None                 # fallback path
    assert doc.guardrail.ok is True          # template invents nothing
    assert "Acme" in doc.content and "Rakesh Naini" in doc.content


def test_linkedin_message_respects_length(monkeypatch):
    monkeypatch.setattr("app.generation.documents.AiGateway.chat",
                        lambda *a, **k: (_ for _ in ()).throw(AiUnavailable("no ai")))
    doc = generate("LINKEDIN_MESSAGE", candidate_name="Rakesh",
                   resume_text="Java developer.", overlap_skills=["Java"],
                   job_title="Engineer", job_company="Acme", job_description="x")
    assert len(doc.content) <= 300


# ---- assistant (integration) ----------------------------------------------
def test_assistant_conversation_and_reply(client):
    from tests.test_auth import auth_headers, register
    pair = register(client).json()
    headers = auth_headers(pair)

    conv = client.post("/api/v1/assistant/conversations",
                       json={"title": "Job hunt"}, headers=headers)
    assert conv.status_code == 201
    conv_id = conv.json()["id"]

    reply = client.post(f"/api/v1/assistant/conversations/{conv_id}/messages",
                        json={"content": "what's my status this week?"},
                        headers=headers)
    assert reply.status_code == 200
    body = reply.json()
    assert "application" in body["content"].lower() or "job" in body["content"].lower()

    # action detection
    scrape = client.post(f"/api/v1/assistant/conversations/{conv_id}/messages",
                        json={"content": "go find new jobs for me"}, headers=headers)
    assert scrape.json()["action"] == "scrape"

    # persisted history
    detail = client.get(f"/api/v1/assistant/conversations/{conv_id}",
                       headers=headers).json()
    assert len(detail["messages"]) == 4      # 2 user + 2 assistant


def test_assistant_conversation_isolated_per_user(client):
    from tests.test_auth import auth_headers, register
    owner = register(client).json()
    conv_id = client.post("/api/v1/assistant/conversations", json={},
                         headers=auth_headers(owner)).json()["id"]
    other = register(client, email="other@example.com").json()
    r = client.get(f"/api/v1/assistant/conversations/{conv_id}",
                  headers=auth_headers(other))
    assert r.status_code == 404
