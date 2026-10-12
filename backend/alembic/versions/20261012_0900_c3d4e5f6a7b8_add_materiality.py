"""Add materiality (flag leadsheet accounts with no supporting docs)

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-10-12

Guarded on purpose: see 20261008_0000_a1b2c3d4e5f6_add_document_account_links.py -- on a
fresh database Base.metadata.create_all builds this table from the model; this migration
only matters for an existing installation upgrading in place.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def _table_names() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return set(inspector.get_table_names())


def upgrade() -> None:
    names = _table_names()
    if "materiality" in names or "fiscal_years" not in names:
        return

    op.create_table(
        "materiality",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "fiscal_year_id",
            sa.Integer(),
            sa.ForeignKey("fiscal_years.id", name="fk_materiality_fiscal_year"),
            nullable=False,
        ),
        sa.Column("overall_materiality", sa.Numeric(15, 2), nullable=False),
        sa.Column("performance_materiality", sa.Numeric(15, 2), nullable=True),
        sa.Column("trivial_threshold", sa.Numeric(15, 2), nullable=True),
        sa.Column("basis", sa.String(length=200), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column(
            "set_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", name="fk_materiality_user"),
            nullable=False,
        ),
        sa.Column("set_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fiscal_year_id", name="uq_materiality_fiscal_year"),
    )
    op.create_index("ix_materiality_fiscal_year_id", "materiality", ["fiscal_year_id"])


def downgrade() -> None:
    if "materiality" in _table_names():
        op.drop_table("materiality")
