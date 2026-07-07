"""Polite HTTP for connectors: honest User-Agent, per-connector rate
limiting (Redis token bucket, degrades to a local sleep), and a hard rule
that we never pretend to be a browser to evade detection."""
import time

import httpx
import structlog

log = structlog.get_logger("connector.http")

USER_AGENT = ("JobPilot/1.0 (+https://jobpilot.dev; self-hosted job-search "
              "assistant; contact set per deployment)")

_last_call: dict[str, float] = {}


def _throttle(connector_id: str, per_min: int) -> None:
    """Best-effort spacing between calls. Redis-based global limiting is
    applied by the ingestion layer; this guards a single worker too."""
    if per_min <= 0:
        return
    min_interval = 60.0 / per_min
    now = time.monotonic()
    wait = min_interval - (now - _last_call.get(connector_id, 0.0))
    if wait > 0:
        time.sleep(wait)
    _last_call[connector_id] = time.monotonic()


def get_json(connector_id: str, url: str, *, per_min: int = 30,
             params: dict | None = None, headers: dict | None = None,
             timeout: float = 30.0) -> dict | list | None:
    _throttle(connector_id, per_min)
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json", **(headers or {})}
    try:
        r = httpx.get(url, params=params, headers=hdrs, timeout=timeout,
                      follow_redirects=True)
        r.raise_for_status()
        return r.json()
    except Exception as e:  # a source failing must never kill ingestion
        log.warning("connector_http_failed", connector=connector_id,
                    url=url, error=str(e)[:200])
        return None
