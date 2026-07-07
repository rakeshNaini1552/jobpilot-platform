"""FastAPI application factory."""
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.admin.router import router as admin_router
from app.analytics.router import router as analytics_router
from app.application.router import router as application_router
from app.assistant.router import router as assistant_router
from app.auth.router import router as auth_router
from app.connector.router import router as jobs_router
from app.connector.router import runs_router
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.settings import get_settings
from app.generation.router import router as documents_router
from app.health.router import router as health_router
from app.matching.router import router as matches_router
from app.resume.router import router as resume_router
from app.user.router import router as user_router

log = structlog.get_logger("app")

ROUTERS = [
    health_router, auth_router, user_router, resume_router, jobs_router,
    runs_router, matches_router, application_router, documents_router,
    assistant_router, analytics_router, admin_router,
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    log.info("startup", env=get_settings().env)
    yield
    log.info("shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="JobPilot Platform API",
        version="1.0.0",
        lifespan=lifespan,
        openapi_url=f"{settings.api_prefix}/openapi.json",
        docs_url=f"{settings.api_prefix}/docs",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)
    for router in ROUTERS:
        app.include_router(router, prefix=settings.api_prefix)
    return app


app = create_app()
