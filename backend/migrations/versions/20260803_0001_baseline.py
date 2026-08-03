"""Create the immutable 27-table DataHub baseline.

Revision ID: 20260803_0001
Revises: None
"""

from __future__ import annotations

from alembic import op

from migrations.baseline_schema import BASELINE_REVISION, build_baseline_metadata


revision: str = BASELINE_REVISION
down_revision: None = None
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    metadata = build_baseline_metadata(connection.dialect.name)
    metadata.create_all(bind=connection, checkfirst=False)


def downgrade() -> None:
    raise RuntimeError(
        "The DataHub baseline downgrade is intentionally disabled; "
        "destructive schema rollback is not supported."
    )
