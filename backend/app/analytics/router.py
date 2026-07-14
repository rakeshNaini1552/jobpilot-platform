"""Analytics endpoints — composite dashboard payload + trends."""
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.api import CurrentUser
from app.core.db import get_session

from . import service
from .schemas import DashboardOut, TrendsOut

router = APIRouter(prefix="/analytics", tags=["analytics"])

Session = Annotated[AsyncSession, Depends(get_session)]


@router.get("/dashboard", response_model=DashboardOut)
async def get_dashboard(session: Session, user: CurrentUser) -> DashboardOut:
    return DashboardOut(**await service.dashboard(session, user.id))


@router.get("/trends", response_model=TrendsOut)
async def get_trends(session: Session, user: CurrentUser,
                     days: int = Query(default=30, ge=7, le=180)) -> TrendsOut:
    return TrendsOut(**await service.trends(session, user.id, days))
