"""
Optimistic locking for critical financial records (PLAN §8.1).

Two people editing the same trial balance entry or budget request at once must not
silently overwrite each other. Clients echo back the ``version`` they loaded; a mismatch
means somebody else saved in the meantime and the request is rejected with 409 rather
than applied.
"""
from __future__ import annotations

from typing import Any, Optional


class VersionConflict(Exception):
    """Raised when a client's version does not match the stored record."""

    def __init__(self, resource_type: str, resource_id: int, expected: int, actual: int):
        super().__init__(
            f"{resource_type} {resource_id} was changed by someone else "
            f"(you had version {expected}, the record is at version {actual})"
        )
        self.resource_type = resource_type
        self.resource_id = resource_id
        self.expected = expected
        self.actual = actual


def check_version(record: Any, expected: Optional[int], resource_type: str = "record") -> None:
    """Verify the client's version against the stored one. ``None`` means 'do not check'."""
    if expected is None:
        return
    actual = int(getattr(record, "version", 1) or 1)
    if int(expected) != actual:
        raise VersionConflict(resource_type, getattr(record, "id", 0), int(expected), actual)


def bump(record: Any) -> None:
    """Increment the record's version after a successful write."""
    record.version = int(getattr(record, "version", 1) or 1) + 1
