"""Auth endpoints — see api/openapi.yaml (tag: auth)."""
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from app.core.db import get_session
from app.core.ratelimit import enforce_rate_limit

from . import oauth, service
from .api import CurrentUser
from .schemas import ForgotIn, LoginIn, LogoutIn, RefreshIn, RegisterIn, ResetIn, TokenPairOut

router = APIRouter(prefix="/auth", tags=["auth"])

Session = Annotated[AsyncSession, Depends(get_session)]


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.post("/register", response_model=TokenPairOut, status_code=201)
async def register(body: RegisterIn, request: Request, session: Session):
    await enforce_rate_limit(f"register:{_ip(request)}", limit=5)
    pair = await service.register(session, body.email, body.password,
                                  body.full_name, _ip(request))
    await session.commit()
    return pair


@router.post("/login", response_model=TokenPairOut)
async def login(body: LoginIn, request: Request, session: Session):
    await enforce_rate_limit(f"login:{_ip(request)}", limit=10)
    pair = await service.login(session, body.email, body.password,
                               _ip(request), request.headers.get("user-agent"))
    await session.commit()
    return pair


@router.post("/refresh", response_model=TokenPairOut)
async def refresh(body: RefreshIn, request: Request, session: Session):
    pair = await service.refresh(session, body.refresh_token, _ip(request))
    await session.commit()
    return pair


@router.post("/logout", status_code=204)
async def logout(body: LogoutIn, request: Request, session: Session,
                 user: CurrentUser) -> Response:
    await service.logout(session, body.refresh_token, user.id, _ip(request))
    await session.commit()
    return Response(status_code=204)


@router.post("/password/forgot", status_code=202)
async def forgot_password(body: ForgotIn, request: Request, session: Session):
    await enforce_rate_limit(f"forgot:{_ip(request)}", limit=5)
    await service.forgot_password(session, body.email)
    await session.commit()
    return {"status": "accepted"}


@router.post("/password/reset", status_code=204)
async def reset_password(body: ResetIn, session: Session) -> Response:
    await service.reset_password(session, body.token, body.new_password)
    await session.commit()
    return Response(status_code=204)


@router.get("/oauth/{provider}/authorize", status_code=302)
async def oauth_authorize(provider: str) -> RedirectResponse:
    return RedirectResponse(oauth.authorize_url(provider), status_code=302)


@router.get("/oauth/{provider}/callback", response_model=TokenPairOut)
async def oauth_callback(provider: str, code: str, state: str,
                         request: Request, session: Session):
    pair = await oauth.handle_callback(session, provider, code, state, _ip(request))
    await session.commit()
    return pair
