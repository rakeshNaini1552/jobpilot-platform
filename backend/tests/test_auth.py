"""Integration tests: full auth lifecycle against a real PostgreSQL."""
import pytest

EMAIL = "rakesh@example.com"
PASSWORD = "supersecret-123"


def register(client, email=EMAIL, password=PASSWORD, name="Rakesh Naini"):
    return client.post("/api/v1/auth/register",
                       json={"email": email, "password": password, "full_name": name})


def login(client, email=EMAIL, password=PASSWORD):
    return client.post("/api/v1/auth/login",
                       json={"email": email, "password": password})


def auth_headers(pair: dict) -> dict:
    return {"Authorization": f"Bearer {pair['access_token']}"}


# ---------------------------------------------------------------- register/login
def test_first_user_becomes_admin_then_users(client):
    r1 = register(client)
    assert r1.status_code == 201
    assert r1.json()["user"]["role"] == "ADMIN"

    r2 = register(client, email="second@example.com")
    assert r2.status_code == 201
    assert r2.json()["user"]["role"] == "USER"


def test_duplicate_email_is_409_problem(client):
    register(client)
    r = register(client)
    assert r.status_code == 409
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["title"] == "Email already registered"


def test_login_and_me(client):
    register(client)
    r = login(client)
    assert r.status_code == 200
    pair = r.json()
    me = client.get("/api/v1/users/me", headers=auth_headers(pair))
    assert me.status_code == 200
    assert me.json()["email"] == EMAIL


def test_login_wrong_password_401(client):
    register(client)
    r = login(client, password="wrong-password-1")
    assert r.status_code == 401


def test_me_requires_valid_token(client):
    assert client.get("/api/v1/users/me").status_code == 401
    r = client.get("/api/v1/users/me",
                   headers={"Authorization": "Bearer not-a-jwt"})
    assert r.status_code == 401


# ---------------------------------------------------------------- refresh rotation
def test_refresh_rotates_and_detects_reuse(client):
    pair0 = register(client).json()

    r1 = client.post("/api/v1/auth/refresh",
                     json={"refresh_token": pair0["refresh_token"]})
    assert r1.status_code == 200
    pair1 = r1.json()
    assert pair1["refresh_token"] != pair0["refresh_token"]

    # Re-using the rotated token = theft signal → 401 and ALL sessions revoked
    reuse = client.post("/api/v1/auth/refresh",
                        json={"refresh_token": pair0["refresh_token"]})
    assert reuse.status_code == 401
    assert "reuse" in reuse.json()["title"].lower()

    revoked_chain = client.post("/api/v1/auth/refresh",
                                json={"refresh_token": pair1["refresh_token"]})
    assert revoked_chain.status_code == 401


def test_logout_revokes_refresh_token(client):
    pair = register(client).json()
    r = client.post("/api/v1/auth/logout",
                    json={"refresh_token": pair["refresh_token"]},
                    headers=auth_headers(pair))
    assert r.status_code == 204
    r = client.post("/api/v1/auth/refresh",
                    json={"refresh_token": pair["refresh_token"]})
    assert r.status_code == 401


# ---------------------------------------------------------------- password reset
def test_password_reset_flow(client, monkeypatch):
    captured: dict = {}
    monkeypatch.setattr("app.auth.service.send_password_reset",
                        lambda email, token: captured.update(token=token))
    pair = register(client).json()

    r = client.post("/api/v1/auth/password/forgot", json={"email": EMAIL})
    assert r.status_code == 202
    # Unknown email gets the same 202 (no account enumeration)
    r = client.post("/api/v1/auth/password/forgot", json={"email": "nobody@x.com"})
    assert r.status_code == 202
    assert "token" in captured

    r = client.post("/api/v1/auth/password/reset",
                    json={"token": captured["token"],
                          "new_password": "brand-new-pass-9"})
    assert r.status_code == 204

    assert login(client).status_code == 401                       # old password dead
    assert login(client, password="brand-new-pass-9").status_code == 200
    # every pre-reset session is revoked
    r = client.post("/api/v1/auth/refresh",
                    json={"refresh_token": pair["refresh_token"]})
    assert r.status_code == 401
    # reset token is single-use
    r = client.post("/api/v1/auth/password/reset",
                    json={"token": captured["token"],
                          "new_password": "another-pass-10"})
    assert r.status_code == 400


# ---------------------------------------------------------------- profile/preferences
def test_patch_me(client):
    pair = register(client).json()
    r = client.patch("/api/v1/users/me", json={"timezone": "America/New_York"},
                     headers=auth_headers(pair))
    assert r.status_code == 200
    assert r.json()["timezone"] == "America/New_York"


def test_preferences_roundtrip(client):
    pair = register(client).json()
    headers = auth_headers(pair)

    r = client.get("/api/v1/users/me/preferences", headers=headers)
    assert r.status_code == 200
    assert r.json()["employment_types"] == ["FULL_TIME"]          # seeded on register

    body = {
        "desired_titles": ["Java Developer", "Backend Engineer"],
        "employment_types": ["FULL_TIME", "CONTRACT"],
        "contract_arrangements": ["W2", "C2C"],
        "workplace_types": ["REMOTE", "HYBRID"],
        "locations": [{"city": "Frisco", "state": "TX", "country": "US", "radius_mi": 30}],
        "countries": ["US"],
        "seniority": "MID",
        "years_experience": "6.0",
        "needs_sponsorship": False,
        "salary_min": 120000,
        "salary_max": 160000,
        "auto_apply_enabled": True,
        "auto_apply_min_score": "70",
        "auto_apply_daily_cap": 25,
    }
    r = client.put("/api/v1/users/me/preferences", json=body, headers=headers)
    assert r.status_code == 200, r.text

    got = client.get("/api/v1/users/me/preferences", headers=headers).json()
    assert got["contract_arrangements"] == ["W2", "C2C"]
    assert got["locations"][0]["city"] == "Frisco"
    assert got["auto_apply_enabled"] is True


# ---------------------------------------------------------------- rbac
async def test_require_admin_rejects_user_role():
    from app.auth.api import require_admin
    from app.core.errors import Problem
    from app.user.models import User

    with pytest.raises(Problem) as exc:
        await require_admin(User(role="USER"))
    assert exc.value.status == 403


# ---------------------------------------------------------------- oauth
def test_oauth_authorize_redirects_with_state(client):
    r = client.get("/api/v1/auth/oauth/google/authorize", follow_redirects=False)
    assert r.status_code == 302
    assert "accounts.google.com" in r.headers["location"]
    assert "state=" in r.headers["location"]


def test_oauth_unconfigured_provider_501(client):
    r = client.get("/api/v1/auth/oauth/github/authorize", follow_redirects=False)
    assert r.status_code == 501


def test_oauth_callback_creates_user(client):
    from urllib.parse import parse_qs, urlparse

    import respx

    auth = client.get("/api/v1/auth/oauth/google/authorize", follow_redirects=False)
    state = parse_qs(urlparse(auth.headers["location"]).query)["state"][0]

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://oauth2.googleapis.com/token").respond(
            json={"access_token": "provider-token"})
        mock.get("https://openidconnect.googleapis.com/v1/userinfo").respond(
            json={"sub": "g-123", "email": "rakesh.oauth@example.com",
                  "name": "Rakesh via Google"})
        r = client.get("/api/v1/auth/oauth/google/callback",
                       params={"code": "fake-code", "state": state})
    assert r.status_code == 200, r.text
    pair = r.json()
    assert pair["user"]["email"] == "rakesh.oauth@example.com"
    assert pair["user"]["role"] == "ADMIN"        # first user bootstrap

    me = client.get("/api/v1/users/me", headers=auth_headers(pair))
    assert me.status_code == 200


def test_oauth_callback_bad_state_401(client):
    r = client.get("/api/v1/auth/oauth/google/callback",
                   params={"code": "x", "state": "tampered"})
    assert r.status_code == 401
