"""Liveness and readiness probes."""
from fastapi import APIRouter
from sqlalchemy import text
from starlette.responses import JSONResponse

from app.core.db import async_engine
from app.core.settings import get_settings

router = APIRouter(tags=["public"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/health/ready")
async def ready() -> JSONResponse:
    checks: dict[str, str] = {}

    try:
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "up"
    except Exception:
        checks["database"] = "down"

    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(get_settings().redis_url, socket_connect_timeout=2)
        await r.ping()
        await r.aclose()
        checks["redis"] = "up"
    except Exception:
        checks["redis"] = "down"

    healthy = all(v == "up" for v in checks.values())
    return JSONResponse({"status": "ok" if healthy else "degraded", "checks": checks},
                        status_code=200 if healthy else 503)
