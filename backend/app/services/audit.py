"""
Audit trail (PLAN §8.3).

Every change to financial data is written to ``audit_logs``. This is not optional for
public-sector finance, so the helpers here are called from the API layer on each mutation
and never raise: an audit failure must not roll back the user's work, but it must be
visible in the logs.

``record`` also publishes a notification (PLAN §8.2) so connected clients see the change
live.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Iterable, Optional

from sqlalchemy.orm import Session

from app.models.connector import AuditLog
from app.models.user import User

logger = logging.getLogger(__name__)

# Values longer than this are truncated in the audit record.
MAX_TEXT = 2000

# Fields that must never be written to the audit trail.
REDACTED_FIELDS = {
    "password",
    "hashed_password",
    "encrypted_password",
    "secret_key",
    "fernet_key",
    "access_token",
    "refresh_token",
}


def _clean(value: Any) -> Any:
    """JSON-safe, redacted copy of a value."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {
            k: ("***redacted***" if k.lower() in REDACTED_FIELDS else _clean(v))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, str) and len(value) > MAX_TEXT:
        return value[:MAX_TEXT] + "…"
    return value


def snapshot(obj: Any, fields: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    """Extract an audit-friendly dict from an ORM object (or pass a dict straight through)."""
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    names = list(fields) if fields is not None else [c.name for c in obj.__table__.columns]
    return {n: _clean(getattr(obj, n, None)) for n in names}


def client_ip(request: Any) -> Optional[str]:
    """Best-effort client address, honouring the reverse proxy's X-Forwarded-For."""
    if request is None:
        return None
    forwarded = request.headers.get("x-forwarded-for") if hasattr(request, "headers") else None
    if forwarded:
        return forwarded.split(",")[0].strip()[:45]
    client = getattr(request, "client", None)
    return getattr(client, "host", None)


def record(
    db: Session,
    *,
    user: Optional[User],
    action: str,
    resource_type: str,
    resource_id: Optional[int] = None,
    old: Any = None,
    new: Any = None,
    summary: Optional[str] = None,
    request: Any = None,
    commit: bool = False,
    notify: bool = True,
) -> Optional[AuditLog]:
    """
    Write an audit entry and (optionally) publish it as a notification.

    ``action`` is a short verb phrase ("create", "update", "post", "unpost", "delete",
    "sign_off", "close", "roll_forward", …); ``summary`` is the human-readable line shown
    in the activity feed.
    """
    entry: Optional[AuditLog] = None
    try:
        entry = AuditLog(
            user_id=user.id if user is not None else None,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            old_values=_clean(old) if old is not None else None,
            new_values=_clean(new) if new is not None else None,
            ip_address=client_ip(request),
        )
        db.add(entry)
        if commit:
            db.commit()
            db.refresh(entry)
        else:
            db.flush()
    except Exception:  # pragma: no cover - auditing must never break the request
        logger.exception("Failed to write audit log for %s %s", action, resource_type)
        return None

    if notify and entry is not None:
        try:
            from app.services.events import publish_from_audit

            publish_from_audit(entry, user, summary)
        except Exception:  # pragma: no cover
            logger.exception("Failed to publish notification for audit entry %s", entry.id)

    return entry


def describe(entry: AuditLog, username: Optional[str] = None) -> str:
    """One-line human description of an audit entry, for feeds and CSV export."""
    who = username or (f"user {entry.user_id}" if entry.user_id else "system")
    resource = entry.resource_type.replace("_", " ")
    if entry.resource_id is not None:
        resource = f"{resource} #{entry.resource_id}"
    return f"{who} {entry.action.replace('_', ' ')} {resource}"


def to_json(entry: AuditLog) -> str:
    """Compact JSON representation, used by the activity export."""
    return json.dumps(
        {
            "id": entry.id,
            "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
            "user_id": entry.user_id,
            "action": entry.action,
            "resource_type": entry.resource_type,
            "resource_id": entry.resource_id,
            "ip_address": entry.ip_address,
            "old_values": entry.old_values,
            "new_values": entry.new_values,
        },
        default=str,
    )
