"""
Upgrade safety: an installation created before a column existed must gain it on start.

``Base.metadata.create_all`` creates missing tables but never adds columns to tables that
already exist, so without the sync an upgrade would fail at query time.
"""
from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 — registers every model on Base.metadata
from app.core.database import Base
from app.core.schema_sync import sync_columns


def _engine():
    return create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)


def test_adds_missing_columns_to_an_existing_table():
    engine = _engine()
    with engine.begin() as connection:
        # A working_papers table as it existed before sign-off and versioning existed.
        connection.execute(
            text(
                """
                CREATE TABLE working_papers (
                    id INTEGER PRIMARY KEY,
                    fiscal_year_id INTEGER NOT NULL,
                    folder_path VARCHAR(500) NOT NULL,
                    filename VARCHAR(255) NOT NULL,
                    display_name VARCHAR(500) NOT NULL,
                    file_type VARCHAR(20) NOT NULL,
                    file_size INTEGER NOT NULL,
                    uploaded_by_user_id INTEGER NOT NULL,
                    uploaded_at DATETIME NOT NULL,
                    description TEXT,
                    version_number INTEGER NOT NULL,
                    parent_version_id INTEGER
                )
                """
            )
        )
        connection.execute(
            text(
                "INSERT INTO working_papers (id, fiscal_year_id, folder_path, filename, display_name,"
                " file_type, file_size, uploaded_by_user_id, uploaded_at, version_number)"
                " VALUES (1, 1, '/permanent', 'a.pdf', 'Bylaw', 'pdf', 10, 1, '2025-01-01', 1)"
            )
        )

    added = sync_columns(engine)
    assert "working_papers.requires_reapproval" in added
    assert "working_papers.reviewer_signed_off_at" in added
    assert "working_papers.superseded_at" in added

    columns = {c["name"] for c in inspect(engine).get_columns("working_papers")}
    assert {"requires_reapproval", "preparer_signed_off_at", "reviewer_signed_off_at", "superseded_at"} <= columns

    # The pre-existing row survives and gets the column default.
    with engine.begin() as connection:
        row = connection.execute(text("SELECT display_name, requires_reapproval FROM working_papers")).one()
    assert row[0] == "Bylaw"
    assert row[1] in (0, False)

    # Running it again is a no-op.
    assert sync_columns(engine) == []


def test_creates_tables_that_do_not_exist_yet_and_is_idempotent():
    engine = _engine()
    Base.metadata.create_all(bind=engine)
    assert sync_columns(engine) == []
