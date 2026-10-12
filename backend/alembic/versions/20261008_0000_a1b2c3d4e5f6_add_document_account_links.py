"""Add document_account_links (leadsheet-to-document linking, PLAN §4.3)

Revision ID: a1b2c3d4e5f6
Revises: None (first migration)
Create Date: 2026-10-08

Guarded on purpose: this project's schema is normally created by
``Base.metadata.create_all`` (which makes missing *tables*) plus
``app.core.schema_sync`` (which adds missing *columns*), and the container
entrypoint runs ``alembic upgrade head`` *before* the app starts. On a fresh
database the referenced tables do not exist yet at migration time, so the
migration steps aside and lets ``create_all`` build the table from the model.
Existing installations get the real ``CREATE TABLE`` here.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = None
branch_labels = None
depends_on = None


def _table_names() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return set(inspector.get_table_names())


def upgrade() -> None:
    names = _table_names()
    # Fresh install: create_all (after migrations) will create the table from the model.
    if "document_account_links" in names or "working_papers" not in names:
        return

    op.create_table(
        "document_account_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "working_paper_id",
            sa.Integer(),
            sa.ForeignKey("working_papers.id", name="fk_dal_working_paper"),
            nullable=False,
        ),
        sa.Column("account_code", sa.String(length=30), nullable=False),
        sa.Column(
            "fiscal_year_id",
            sa.Integer(),
            sa.ForeignKey("fiscal_years.id", name="fk_dal_fiscal_year"),
            nullable=False,
        ),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", name="fk_dal_user"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("working_paper_id", "account_code", name="uq_wp_account_link"),
    )
    op.create_index(
        "ix_document_account_links_working_paper_id", "document_account_links", ["working_paper_id"]
    )
    op.create_index("ix_document_account_links_account_code", "document_account_links", ["account_code"])
    op.create_index(
        "ix_document_account_links_fiscal_year_id", "document_account_links", ["fiscal_year_id"]
    )


def downgrade() -> None:
    if "document_account_links" in _table_names():
        op.drop_table("document_account_links")
