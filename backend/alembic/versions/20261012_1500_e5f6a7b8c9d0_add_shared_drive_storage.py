"""Add shared-drive storage columns to working_papers

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-10-12

Guarded like the other document-feature migrations: on a fresh database
Base.metadata.create_all builds these columns from the model already.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    existing = _columns("working_papers")
    if not existing or "storage_backend" in existing:
        return

    op.add_column(
        "working_papers",
        sa.Column("storage_backend", sa.String(length=20), nullable=False, server_default="managed"),
    )
    op.add_column("working_papers", sa.Column("content_hash", sa.String(length=64), nullable=True))
    op.add_column("working_papers", sa.Column("source_mtime", sa.Float(), nullable=True))
    op.add_column("working_papers", sa.Column("missing_since", sa.DateTime(timezone=True), nullable=True))
    op.add_column("working_papers", sa.Column("backup_path", sa.String(length=600), nullable=True))
    op.alter_column("working_papers", "storage_backend", server_default=None)


def downgrade() -> None:
    existing = _columns("working_papers")
    if "storage_backend" not in existing:
        return
    op.drop_column("working_papers", "backup_path")
    op.drop_column("working_papers", "missing_since")
    op.drop_column("working_papers", "source_mtime")
    op.drop_column("working_papers", "content_hash")
    op.drop_column("working_papers", "storage_backend")
