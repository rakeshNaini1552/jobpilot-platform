"""Test infrastructure.

Integration tests run against a REAL PostgreSQL:
- If JOBPILOT_DATABASE_URL is already set (CI: pgvector Testcontainer), use it.
- Else boot a scratch cluster from a local Postgres install (initdb into a
  temp dir), apply the canonical schema with pgvector bits stubbed to text
  (auth/profile tests don't touch embeddings), and tear it all down at exit.
- If no Postgres is available, DB-backed tests skip.

Must run before any `app.*` import: settings are cached and engines bind at
import time, so the database URL is fixed in pytest_configure.
"""
import os
import re
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path

import pytest

_PG: dict = {}

_PG_BIN_CANDIDATES = [
    "/opt/homebrew/opt/postgresql@17/bin",
    "/opt/homebrew/opt/postgresql@16/bin",
    "/opt/homebrew/opt/postgresql@15/bin",
    "/usr/local/opt/postgresql@16/bin",
    "/usr/lib/postgresql/16/bin",
]


def _find_pg_bin() -> str | None:
    for candidate in _PG_BIN_CANDIDATES:
        if (Path(candidate) / "initdb").exists():
            return candidate
    initdb = shutil.which("initdb")
    return str(Path(initdb).parent) if initdb else None


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _stub_pgvector(sql: str) -> str:
    sql = sql.replace("CREATE EXTENSION IF NOT EXISTS vector;", "")
    sql = sql.replace("vector(768)", "text")
    return re.sub(r"CREATE INDEX [^;]*hnsw[^;]*;", "", sql, flags=re.S)


def pytest_configure(config: pytest.Config) -> None:
    os.environ.setdefault("JOBPILOT_GOOGLE_CLIENT_ID", "test-google-id")
    os.environ.setdefault("JOBPILOT_GOOGLE_CLIENT_SECRET", "test-google-secret")

    if os.environ.get("JOBPILOT_DATABASE_URL"):
        _PG["external"] = True
        return

    pg_bin = _find_pg_bin()
    if pg_bin is None:
        _PG["unavailable"] = True
        return

    data_root = Path(tempfile.mkdtemp(prefix="jp_pg_"))
    sock_dir = Path(tempfile.mkdtemp(prefix="jp_s_", dir="/tmp"))
    port = _free_port()
    env = {**os.environ, "LC_ALL": "C"}

    subprocess.run([f"{pg_bin}/initdb", "-D", str(data_root / "data"),
                    "-U", "jobpilot", "--no-locale", "-E", "UTF8"],
                   env=env, check=True, capture_output=True)
    subprocess.run([f"{pg_bin}/pg_ctl", "-D", str(data_root / "data"),
                    "-o", f"-p {port} -c listen_addresses=127.0.0.1 -k {sock_dir}",
                    "-l", str(data_root / "log"), "-w", "start"],
                   env=env, check=True, capture_output=True)
    subprocess.run([f"{pg_bin}/createdb", "-h", "127.0.0.1", "-p", str(port),
                    "-U", "jobpilot", "jobpilot"], env=env, check=True,
                   capture_output=True)

    schema = (Path(__file__).parent.parent / "alembic" / "sql" /
              "0001_initial.sql").read_text(encoding="utf-8")
    subprocess.run([f"{pg_bin}/psql", "-h", "127.0.0.1", "-p", str(port),
                    "-U", "jobpilot", "-d", "jobpilot", "-v", "ON_ERROR_STOP=1",
                    "-q", "-f", "-"],
                   env=env, check=True, capture_output=True,
                   input=_stub_pgvector(schema).encode())

    os.environ["JOBPILOT_DATABASE_URL"] = (
        f"postgresql+psycopg://jobpilot@127.0.0.1:{port}/jobpilot")
    _PG.update(bin=pg_bin, data_root=data_root, sock_dir=sock_dir,
               port=port, env=env)


def pytest_unconfigure(config: pytest.Config) -> None:
    if "bin" not in _PG:
        return
    subprocess.run([f"{_PG['bin']}/pg_ctl", "-D", str(_PG["data_root"] / "data"),
                    "-m", "immediate", "stop"],
                   env=_PG["env"], capture_output=True)
    shutil.rmtree(_PG["data_root"], ignore_errors=True)
    shutil.rmtree(_PG["sock_dir"], ignore_errors=True)


def _truncate_all() -> None:
    """Reset mutable tables between tests, in child→parent order.
    Deliberately NOT CASCADE: the seed tables (connector_settings,
    scheduled_tasks) are referenced by users.updated_by-style FKs, and a
    CASCADE from users would wipe those seeds."""
    from sqlalchemy import create_engine, text
    engine = create_engine(os.environ["JOBPILOT_DATABASE_URL"])  # keep psycopg3 driver
    tables = ["company_watchlist", "job_extractions", "match_scores",
              "generated_documents", "application_events", "application_contacts",
              "applications", "jobs", "companies", "scheduled_runs",
              "audit_events", "refresh_tokens", "password_reset_tokens",
              "oauth_accounts", "preferences", "users"]
    with engine.begin() as conn:
        for table in tables:
            conn.execute(text(f"DELETE FROM {table};"))
    engine.dispose()


@pytest.fixture
def db() -> None:
    """Depend on this to require a real database (skips when unavailable)."""
    if _PG.get("unavailable"):
        pytest.skip("no PostgreSQL available for integration tests")


@pytest.fixture
def client(db):
    """Fresh app + clean tables per test."""
    if "bin" in _PG or os.environ.get("JOBPILOT_DATABASE_URL"):
        _truncate_all()

    from fastapi.testclient import TestClient

    from app.main import create_app
    return TestClient(create_app(), raise_server_exceptions=False)
