"""Database engines & sessions.

- Async engine + session for the API path (FastAPI dependencies).
- Sync engine + session for Celery tasks and Alembic (same URL, psycopg sync).
"""
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .settings import get_settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


_settings = get_settings()

async_engine = create_async_engine(_settings.database_url, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(async_engine, class_=AsyncSession,
                                       expire_on_commit=False)

sync_engine = create_engine(_settings.database_url, pool_pre_ping=True)
SyncSessionLocal = sessionmaker(sync_engine, class_=Session, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency — one transaction-scoped session per request."""
    async with AsyncSessionLocal() as session:
        yield session


@contextmanager
def worker_session() -> Iterator[Session]:
    """Celery-side session with commit/rollback semantics."""
    session = SyncSessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
