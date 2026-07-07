"""structlog configuration: console renderer locally, JSON in prod."""
import logging

import structlog

from .settings import get_settings


def configure_logging() -> None:
    settings = get_settings()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    shared = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    renderer = (structlog.processors.JSONRenderer() if settings.log_json
                else structlog.dev.ConsoleRenderer())
    structlog.configure(
        processors=[*shared, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )
