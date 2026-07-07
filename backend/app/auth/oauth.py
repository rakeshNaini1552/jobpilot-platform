"""OAuth2 login (Google, GitHub) — config-gated, no server-side session:
the `state` parameter is a short-lived signed JWT.

Flow: GET /auth/oauth/{provider}/authorize → 302 to provider →
provider redirects to /auth/oauth/{provider}/callback?code=…&state=… →
code exchanged for the provider profile → account linked/created → TokenPair.
"""
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.audit import audit
from app.core.errors import Problem
from app.core.security import create_state_token, decode_state_token
from app.core.settings import get_settings
from app.user.models import OAuthAccount, Preferences, User

from .service import _issue_pair


@dataclass(frozen=True)
class ProviderConfig:
    authorize_url: str
    token_url: str
    userinfo_url: str
    scope: str

    def client(self) -> tuple[str, str]:
        s = get_settings()
        if self.authorize_url.startswith("https://accounts.google"):
            return s.google_client_id, s.google_client_secret
        return s.github_client_id, s.github_client_secret


PROVIDERS: dict[str, ProviderConfig] = {
    "google": ProviderConfig(
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        userinfo_url="https://openidconnect.googleapis.com/v1/userinfo",
        scope="openid email profile",
    ),
    "github": ProviderConfig(
        authorize_url="https://github.com/login/oauth/authorize",
        token_url="https://github.com/login/oauth/access_token",
        userinfo_url="https://api.github.com/user",
        scope="read:user user:email",
    ),
}


def _provider(name: str) -> ProviderConfig:
    cfg = PROVIDERS.get(name)
    if cfg is None:
        raise Problem(404, "Unknown OAuth provider", type_suffix="oauth-unknown")
    client_id, _ = cfg.client()
    if not client_id:
        raise Problem(501, f"OAuth provider '{name}' is not configured",
                      "Set the client id/secret in settings to enable it.",
                      type_suffix="oauth-unconfigured")
    return cfg


def _redirect_uri(provider: str) -> str:
    return f"{get_settings().oauth_redirect_base}/auth/oauth/{provider}/callback"


def authorize_url(provider: str) -> str:
    cfg = _provider(provider)
    client_id, _ = cfg.client()
    params = {
        "client_id": client_id,
        "redirect_uri": _redirect_uri(provider),
        "response_type": "code",
        "scope": cfg.scope,
        "state": create_state_token({"provider": provider}),
    }
    return f"{cfg.authorize_url}?{urlencode(params)}"


async def _fetch_profile(provider: str, cfg: ProviderConfig, code: str) -> dict:
    client_id, client_secret = cfg.client()
    async with httpx.AsyncClient(timeout=15) as http:
        token_resp = await http.post(cfg.token_url, headers={"Accept": "application/json"},
                                     data={
                                         "client_id": client_id,
                                         "client_secret": client_secret,
                                         "code": code,
                                         "grant_type": "authorization_code",
                                         "redirect_uri": _redirect_uri(provider),
                                     })
        token_resp.raise_for_status()
        access_token = token_resp.json().get("access_token")
        if not access_token:
            raise Problem(401, "OAuth code exchange failed", type_suffix="oauth-exchange")
        info_resp = await http.get(cfg.userinfo_url,
                                   headers={"Authorization": f"Bearer {access_token}"})
        info_resp.raise_for_status()
        return info_resp.json()


async def handle_callback(session: AsyncSession, provider: str,
                          code: str, state: str, ip: str | None = None) -> dict:
    cfg = _provider(provider)
    try:
        claims = decode_state_token(state)
    except Exception as e:  # noqa: BLE001
        raise Problem(401, "Invalid OAuth state", type_suffix="oauth-state") from e
    if claims.get("provider") != provider:
        raise Problem(401, "OAuth state mismatch", type_suffix="oauth-state")

    profile = await _fetch_profile(provider, cfg, code)
    provider_user_id = str(profile.get("sub") or profile.get("id") or "")
    email = (profile.get("email") or "").lower()
    name = profile.get("name") or profile.get("login") or email
    if not provider_user_id:
        raise Problem(401, "Provider returned no user id", type_suffix="oauth-profile")

    account = await session.scalar(select(OAuthAccount).where(
        OAuthAccount.provider == provider,
        OAuthAccount.provider_user_id == provider_user_id))
    if account:
        user = await session.get(User, account.user_id)
    else:
        user = await session.scalar(select(User).where(User.email == email)) if email else None
        if user is None:
            if not email:
                raise Problem(401, "Provider returned no email; cannot create account",
                              type_suffix="oauth-no-email")
            first_user = (await session.scalar(select(User.id).limit(1))) is None
            user = User(email=email, full_name=name,
                        role="ADMIN" if first_user else "USER")
            session.add(user)
            await session.flush()
            session.add(Preferences(user_id=user.id))
        session.add(OAuthAccount(user_id=user.id, provider=provider,
                                 provider_user_id=provider_user_id))
    if not user.is_active:
        raise Problem(401, "Account disabled", type_suffix="account-disabled")
    await audit(session, "auth.oauth_login", user_id=user.id, ip=ip,
                detail={"provider": provider})
    return await _issue_pair(session, user, ip)
