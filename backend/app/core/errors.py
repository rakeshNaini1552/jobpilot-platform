"""RFC-7807 problem+json errors — the single error surface of the API."""
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

log = structlog.get_logger("errors")

PROBLEM_CONTENT_TYPE = "application/problem+json"
PROBLEM_BASE = "https://jobpilot.dev/problems"


class Problem(Exception):
    """Raise anywhere in a service; rendered as RFC-7807."""

    def __init__(self, status: int, title: str, detail: str = "",
                 type_suffix: str = "generic", **extra: Any):
        self.status = status
        self.title = title
        self.detail = detail
        self.type = f"{PROBLEM_BASE}/{type_suffix}"
        self.extra = extra
        super().__init__(detail or title)


def _render(status: int, title: str, detail: str = "",
            type_: str = f"{PROBLEM_BASE}/generic", **extra: Any) -> JSONResponse:
    body = {"type": type_, "title": title, "status": status, "detail": detail, **extra}
    return JSONResponse(body, status_code=status, media_type=PROBLEM_CONTENT_TYPE)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(Problem)
    async def problem_handler(_: Request, exc: Problem) -> JSONResponse:
        return _render(exc.status, exc.title, exc.detail, exc.type, **exc.extra)

    @app.exception_handler(StarletteHTTPException)
    async def http_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _render(exc.status_code, str(exc.detail) or "HTTP error")

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [{"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]}
                  for e in exc.errors()]
        return _render(422, "Validation failed",
                       type_=f"{PROBLEM_BASE}/validation", errors=errors)

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_error", path=request.url.path)
        return _render(500, "Internal server error",
                       "An unexpected error occurred. It has been logged.")
