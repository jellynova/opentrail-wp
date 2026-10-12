"""Add document_cross_links (document-to-document "file linking", PLAN §7)

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-10-11

Guarded on purpose: see 20261008_0000_a1b2c3d4e5f6_add_document_account_links.py — on a
fresh database Base.metadata.create_all builds this table from the model; this migration
only matters for an existing installation upgrading in place.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def _table_names() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return set(inspector.get_table_names())


def upgrade() -> None:
    names = _table_names()
    if "document_cross_links" in names or "working_papers" not in names:
        return

    op.create_table(
        "document_cross_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "document_id",
            sa.Integer(),
            sa.ForeignKey("working_papers.id", name="fk_dcl_document"),
            nullable=False,
        ),
        sa.Column(
            "related_document_id",
            sa.Integer(),
            sa.ForeignKey("working_papers.id", name="fk_dcl_related_document"),
            nullable=False,
        ),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", name="fk_dcl_user"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "related_document_id", name="uq_document_cross_link"),
    )
    op.create_index("ix_document_cross_links_document_id", "document_cross_links", ["document_id"])
    op.create_index(
        "ix_document_cross_links_related_document_id", "document_cross_links", ["related_document_id"]
    )


def downgrade() -> None:
    if "document_cross_links" in _table_names():
        op.drop_table("document_cross_links")
