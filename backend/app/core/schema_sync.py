"""
Additive schema sync for existing installations.

The app creates its schema with ``Base.metadata.create_all``, which creates missing
*tables* but never adds missing *columns* to a table that already exists. That is fine for
a fresh install and silently breaks an upgrade: a deployment created before a new column
was introduced would keep running against the old shape and fail at query time.

``sync_columns`` closes that gap for the only change we make in practice — new columns —
by adding them with ``ALTER TABLE ... ADD COLUMN``. It is deliberately conservative:

* it never drops, renames or retypes anything;
* it skips columns whose table does not exist yet (``create_all`` just made them);
* a ``NOT NULL`` column is only added when a default can be derived, and is emitted with
  that default so existing rows are valid;
* anything it cannot do safely is logged and skipped rather than guessed at.

Real migrations (backfills, type changes, renames) still belong in Alembic.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.core.database import Base

logger = logging.getLogger(__name__)


def _literal_default(column: Any) -> str | None:
    """SQL literal for a column's default, or None when we cannot derive one."""
    default = column.default
    if default is None or not getattr(default, "is_scalar", False):
        return None
    value = default.arg
    if callable(value):
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    return None


def sync_columns(engine: Engine) -> List[str]:
    """
    Add any column the models declare but the database is missing.

    Returns the list of ``table.column`` names that were added, so the caller can log them.
    """
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    added: List[str] = []

    for table_name, table in Base.metadata.tables.items():
        if table_name not in existing_tables:
            continue
        existing_columns: Dict[str, Any] = {c["name"]: c for c in inspector.get_columns(table_name)}
        for column in table.columns:
            if column.name in existing_columns:
                continue

            ddl = column.type.compile(dialect=engine.dialect)
            if not column.nullable:
                default = _literal_default(column)
                if default is None:
                    logger.warning(
                        "Column %s.%s is missing but NOT NULL without a default; "
                        "add it manually or via an Alembic migration",
                        table_name,
                        column.name,
                    )
                    continue
                ddl = f"{ddl} DEFAULT {default} NOT NULL"

            statement = f'ALTER TABLE "{table_name}" ADD COLUMN "{column.name}" {ddl}'
            try:
                with engine.begin() as connection:
                    connection.execute(text(statement))
                added.append(f"{table_name}.{column.name}")
                logger.info("Added missing column %s.%s", table_name, column.name)
            except Exception:
                logger.exception("Could not add column %s.%s (%s)", table_name, column.name, statement)

    return added
