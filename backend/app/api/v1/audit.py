"""
Audit trail API (PLAN §8.3): browse and export the activity log.

Read access is limited to the finance team (admin and officer) — the log records who
touched which figures, which is accountability data rather than report data.
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, time
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_role
from app.models.connector import AuditLog
from app.models.user import User
from app.schemas.audit import AuditLogResponse, AuditLogPage
from app.services import audit as audit_svc

router = APIRouter()

READ_ROLES = ("finance_admin", "finance_officer")


def _query(
    db: Session,
    *,
    resource_type: Optional[str],
    resource_id: Optional[int],
    user_id: Optional[int],
    action: Optional[str],
    date_from: Optional[date],
    date_to: Optional[date],
):
    stmt = select(AuditLog)
    if resource_type:
        stmt = stmt.where(AuditLog.resource_type == resource_type)
    if resource_id is not None:
        stmt = stmt.where(AuditLog.resource_id == resource_id)
    if user_id is not None:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if date_from is not None:
        stmt = stmt.where(AuditLog.timestamp >= datetime.combine(date_from, time.min))
    if date_to is not None:
        stmt = stmt.where(AuditLog.timestamp <= datetime.combine(date_to, time.max))
    return stmt


@router.get("/audit-logs", response_model=AuditLogPage)
def list_audit_logs(
    resource_type: Optional[str] = Query(None),
    resource_id: Optional[int] = Query(None),
    user_id: Optional[int] = Query(None),
    action: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*READ_ROLES)),
):
    """Newest-first page of audit entries, with the usernames joined in."""
    stmt = _query(
        db,
        resource_type=resource_type,
        resource_id=resource_id,
        user_id=user_id,
        action=action,
        date_from=date_from,
        date_to=date_to,
    ).order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())

    rows = db.scalars(stmt.limit(limit + 1).offset(offset)).all()
    has_more = len(rows) > limit
    rows = rows[:limit]

    usernames = {
        u.id: u.username
        for u in db.scalars(select(User).where(User.id.in_({r.user_id for r in rows if r.user_id}))).all()
    }
    items = [
        AuditLogResponse(
            id=r.id,
            user_id=r.user_id,
            username=usernames.get(r.user_id),
            action=r.action,
            resource_type=r.resource_type,
            resource_id=r.resource_id,
            old_values=r.old_values,
            new_values=r.new_values,
            ip_address=r.ip_address,
            timestamp=r.timestamp,
            description=audit_svc.describe(r, usernames.get(r.user_id)),
        )
        for r in rows
    ]
    return AuditLogPage(items=items, limit=limit, offset=offset, has_more=has_more)


@router.get("/audit-logs/export")
def export_audit_logs(
    resource_type: Optional[str] = Query(None),
    resource_id: Optional[int] = Query(None),
    user_id: Optional[int] = Query(None),
    action: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*READ_ROLES)),
):
    """CSV export of the filtered activity log (auditor evidence)."""
    stmt = _query(
        db,
        resource_type=resource_type,
        resource_id=resource_id,
        user_id=user_id,
        action=action,
        date_from=date_from,
        date_to=date_to,
    ).order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())

    rows = db.scalars(stmt).all()
    usernames = {
        u.id: u.username
        for u in db.scalars(select(User).where(User.id.in_({r.user_id for r in rows if r.user_id}))).all()
    }

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Timestamp", "User", "Action", "Resource type", "Resource id", "IP address", "Description"])
    for r in rows:
        writer.writerow([
            r.timestamp.isoformat() if r.timestamp else "",
            usernames.get(r.user_id, ""),
            r.action,
            r.resource_type,
            r.resource_id if r.resource_id is not None else "",
            r.ip_address or "",
            audit_svc.describe(r, usernames.get(r.user_id)),
        ])

    filename = "opentrail-activity-log.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
