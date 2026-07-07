"""Fixed-window rate limiter on Redis with graceful degradation:
if Redis is unreachable the request proceeds (availability over strictness
for a self-hosted tool) and the incident is logged."""
import structlog

from app.core.errors import Problem
from app.core.settings import get_settings

log = structlog.get_logger("ratelimit")


async def enforce_rate_limit(key: str, limit: int, window_seconds: int = 60) -> None:
    """Raise Problem(429) when `key` exceeds `limit` per window."""
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(get_settings().redis_url, socket_connect_timeout=1)
        try:
            bucket = f"rl:{key}"
            count = await r.incr(bucket)
            if count == 1:
                await r.expire(bucket, window_seconds)
            if count > limit:
                raise Problem(429, "Too many requests",
                              f"Rate limit exceeded; retry in up to {window_seconds}s.",
                              type_suffix="rate-limit")
        finally:
            await r.aclose()
    except Problem:
        raise
    except Exception as e:  # Redis down — degrade open
        log.warning("ratelimit_degraded", key=key, error=str(e))
