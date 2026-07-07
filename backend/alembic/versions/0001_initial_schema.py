"""Initial schema — executes the canonical Phase 2 DDL (alembic/sql/0001_initial.sql).

Revision ID: 0001
Revises:
"""
from pathlib import Path

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

_SQL = Path(__file__).parent.parent / "sql" / "0001_initial.sql"


def upgrade() -> None:
    op.execute(_SQL.read_text(encoding="utf-8"))


def downgrade() -> None:
    raise NotImplementedError(
        "0001 is the baseline; drop and recreate the database instead."
    )
