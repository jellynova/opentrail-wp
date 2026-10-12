"""Add account_comments (explain a variance without attaching a document)

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-10-12

Guarded on purpose: see 20261008_0000_a1b2c3d4e5f6_add_document_account_links.py -- on a
fresh database Base.metadata.create_all builds this table from the model; this migration
only matters for an existing installation upgrading in place.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def _table_names() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return set(inspector.get_table_names())


def upgrade() -> None:
    names = _table_names()
    if "account_comments" in names or "fiscal_years" not in names:
        return

    op.create_table(
        "account_comments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_code", sa.String(length=30), nullable=False),
        sa.Column(
            "fiscal_year_id",
            sa.Integer(),
            sa.ForeignKey("fiscal_years.id", name="fk_account_comments_fiscal_year"),
            nullable=False,
        ),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", name="fk_account_comments_created_by"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_resolved", sa.Boolean(), nullable=False),
        sa.Column(
            "resolved_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", name="fk_account_comments_resolved_by"),
            nullable=True,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_account_comments_account_code", "account_comments", ["account_code"])
    op.create_index("ix_account_comments_fiscal_year_id", "account_comments", ["fiscal_year_id"])


def downgrade() -> None:
    if "account_comments" in _table_names():
        op.drop_table("account_comments")
