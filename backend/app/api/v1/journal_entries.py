import re
from decimal import Decimal
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_active_user, require_role
from app.models.account import Account
from app.models.journal_entry import JournalEntry, JournalLine
from app.models.period import FiscalYear, Period
from app.models.user import User
from app.services import audit as audit_svc
from app.services import locking
from app.schemas.journal_entry import (
    JournalEntryCreate,
    JournalEntryUpdate,
    JournalEntryResponse,
    JournalLineCreate,
)

router = APIRouter()

REFERENCE_PREFIX = {
    "adjusting": "AJE",
    "reclassifying": "RJE",
    "elimination": "EJE",
    "budget_variance": "BJE",
}


def _conflict(exc: "locking.VersionConflict") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=str(exc),
        headers={"X-Conflict-Reason": "stale-version"},
    )


def _entry_snapshot(entry: JournalEntry) -> dict:
    return {
        "reference": entry.reference,
        "description": entry.description,
        "entry_type": entry.entry_type,
        "status": entry.status,
        "period_id": entry.period_id,
        "lines": [
            {
                "account_id": l.account_id,
                "debit": str(l.debit),
                "credit": str(l.credit),
                "description": l.description,
            }
            for l in entry.lines
        ],
    }


def _get_entry_or_404(db: Session, entry_id: int) -> JournalEntry:
    entry = db.get(JournalEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Journal entry not found")
    return entry


def _get_open_period(db: Session, period_id: int) -> Period:
    """Return the period, rejecting closed periods and closed/locked fiscal years."""
    period = db.get(Period, period_id)
    if period is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Period not found")
    if period.is_closed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Period '{period.name}' is closed")
    fy = db.get(FiscalYear, period.fiscal_year_id)
    if fy is not None and fy.status != "open":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Fiscal year {fy.label} is {fy.status}"
        )
    return period


def _validate_line_accounts(db: Session, period: Period, lines: List[JournalLineCreate]) -> None:
    account_ids = {l.account_id for l in lines}
    accounts = db.scalars(select(Account).where(Account.id.in_(account_ids))).all()
    found = {a.id: a for a in accounts}
    missing = sorted(account_ids - found.keys())
    if missing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown account id(s): {missing}")
    wrong_year = sorted(a.acct_fmtd for a in accounts if a.fiscal_year_id != period.fiscal_year_id)
    if wrong_year:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Account(s) not in the period's fiscal year: {wrong_year}",
        )


def _next_reference(db: Session, period: Period, entry_type: str) -> str:
    """Next sequential reference for the entry type within the fiscal year, e.g. AJE-004."""
    prefix = REFERENCE_PREFIX[entry_type]
    refs = db.scalars(
        select(JournalEntry.reference)
        .join(Period, JournalEntry.period_id == Period.id)
        .where(Period.fiscal_year_id == period.fiscal_year_id, JournalEntry.entry_type == entry_type)
    ).all()
    pattern = re.compile(rf"^{prefix}-(\d+)$")
    numbers = [int(m.group(1)) for r in refs if r and (m := pattern.match(r))]
    return f"{prefix}-{(max(numbers, default=0) + 1):03d}"


def _add_lines(db: Session, entry: JournalEntry, lines: List[JournalLineCreate]) -> None:
    for line_data in lines:
        db.add(
            JournalLine(
                journal_entry_id=entry.id,
                account_id=line_data.account_id,
                debit=line_data.debit,
                credit=line_data.credit,
                description=line_data.description,
                gl_reference=line_data.gl_reference,
            )
        )


@router.get("/journal-entries", response_model=List[JournalEntryResponse])
def list_journal_entries(
    period_id: Optional[int] = Query(None),
    fiscal_year_id: Optional[int] = Query(None),
    entry_type: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: Optional[int] = Query(None, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    stmt = select(JournalEntry).order_by(JournalEntry.entry_date.desc(), JournalEntry.id.desc())
    if period_id is not None:
        stmt = stmt.where(JournalEntry.period_id == period_id)
    if fiscal_year_id is not None:
        stmt = stmt.join(Period, JournalEntry.period_id == Period.id).where(Period.fiscal_year_id == fiscal_year_id)
    if entry_type:
        stmt = stmt.where(JournalEntry.entry_type == entry_type)
    if status_filter:
        stmt = stmt.where(JournalEntry.status == status_filter)
    if limit:
        stmt = stmt.limit(limit)
    return db.scalars(stmt).all()


@router.post("/journal-entries", response_model=JournalEntryResponse, status_code=status.HTTP_201_CREATED)
def create_journal_entry(
    data: JournalEntryCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer")),
):
    """Create a journal entry with its lines in draft status."""
    if not data.lines:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Journal entry must have at least one line")

    period = _get_open_period(db, data.period_id)
    _validate_line_accounts(db, period, data.lines)

    entry = JournalEntry(
        period_id=data.period_id,
        entry_date=data.entry_date,
        reference=data.reference or _next_reference(db, period, data.entry_type),
        description=data.description,
        entry_type=data.entry_type,
        prepared_by_user_id=current_user.id,
        status="draft",
    )
    db.add(entry)
    db.flush()  # get entry.id
    _add_lines(db, entry, data.lines)
    db.flush()

    audit_svc.record(
        db,
        user=current_user,
        action="create",
        resource_type="journal_entry",
        resource_id=entry.id,
        new=_entry_snapshot(entry),
        summary=f"created journal entry {entry.reference or entry.id}",
        request=request,
    )
    db.commit()
    db.refresh(entry)
    return entry


@router.get("/journal-entries/{entry_id}", response_model=JournalEntryResponse)
def get_journal_entry(
    entry_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return _get_entry_or_404(db, entry_id)


@router.put("/journal-entries/{entry_id}", response_model=JournalEntryResponse)
def update_journal_entry(
    entry_id: int,
    data: JournalEntryUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer")),
):
    """Update a journal entry. Only permitted when status is 'draft'."""
    entry = _get_entry_or_404(db, entry_id)
    try:
        locking.check_version(entry, data.version, "journal entry")
    except locking.VersionConflict as exc:
        raise _conflict(exc)
    if entry.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot edit a journal entry with status '{entry.status}'",
        )
    period = _get_open_period(db, entry.period_id)
    before = _entry_snapshot(entry)

    if data.entry_date is not None:
        entry.entry_date = data.entry_date
    if data.reference is not None:
        entry.reference = data.reference
    if data.description is not None:
        entry.description = data.description
    if data.entry_type is not None:
        entry.entry_type = data.entry_type

    if data.lines is not None:
        if not data.lines:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Journal entry must have at least one line")
        _validate_line_accounts(db, period, data.lines)
        # Replace all lines
        for old_line in list(entry.lines):
            db.delete(old_line)
        db.flush()
        _add_lines(db, entry, data.lines)

    db.flush()
    locking.bump(entry)
    audit_svc.record(
        db,
        user=current_user,
        action="update",
        resource_type="journal_entry",
        resource_id=entry.id,
        old=before,
        new=_entry_snapshot(entry),
        summary=f"edited journal entry {entry.reference or entry.id}",
        request=request,
    )
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/journal-entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_journal_entry(
    entry_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer")),
):
    """Delete a draft journal entry. Posted/approved entries must be unposted first."""
    entry = _get_entry_or_404(db, entry_id)
    if entry.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only draft entries can be deleted; current status is '{entry.status}'",
        )
    audit_svc.record(
        db,
        user=current_user,
        action="delete",
        resource_type="journal_entry",
        resource_id=entry.id,
        old=_entry_snapshot(entry),
        summary=f"deleted draft journal entry {entry.reference or entry.id}",
        request=request,
    )
    db.delete(entry)
    db.commit()


@router.post("/journal-entries/{entry_id}/post", response_model=JournalEntryResponse)
def post_journal_entry(
    entry_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer")),
):
    """
    Post a journal entry. Debits must equal credits unless JE_BALANCE_ENFORCEMENT is
    "warn", in which case the entry posts and the response reports is_balanced=false.
    """
    entry = _get_entry_or_404(db, entry_id)
    if entry.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Can only post a draft entry; current status is '{entry.status}'",
        )
    _get_open_period(db, entry.period_id)

    if not entry.lines:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot post an entry with no lines")

    total_debit = sum((Decimal(str(l.debit)) for l in entry.lines), Decimal("0"))
    total_credit = sum((Decimal(str(l.credit)) for l in entry.lines), Decimal("0"))

    if total_debit != total_credit and settings.JE_BALANCE_ENFORCEMENT != "warn":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Journal entry is not balanced: debits={total_debit}, credits={total_credit}",
        )

    entry.status = "posted"
    db.flush()
    locking.bump(entry)
    audit_svc.record(
        db,
        user=current_user,
        action="post",
        resource_type="journal_entry",
        resource_id=entry.id,
        new={"status": "posted", "total_debit": str(total_debit), "total_credit": str(total_credit)},
        summary=f"posted journal entry {entry.reference or entry.id}",
        request=request,
    )
    db.commit()
    db.refresh(entry)
    return entry


@router.post("/journal-entries/{entry_id}/unpost", response_model=JournalEntryResponse)
def unpost_journal_entry(
    entry_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer")),
):
    """
    Return an entry to draft so it can be corrected. Reopening an approved entry
    requires finance_admin and clears the reviewer sign-off.
    """
    entry = _get_entry_or_404(db, entry_id)
    if entry.status == "draft":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Entry is already a draft")
    if entry.status == "approved" and current_user.role != "finance_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Only a finance_admin can reopen an approved entry"
        )
    _get_open_period(db, entry.period_id)

    previous_status = entry.status
    entry.status = "draft"
    entry.reviewed_by_user_id = None
    db.flush()
    locking.bump(entry)
    audit_svc.record(
        db,
        user=current_user,
        action="unpost",
        resource_type="journal_entry",
        resource_id=entry.id,
        old={"status": previous_status},
        new={"status": "draft"},
        summary=f"returned journal entry {entry.reference or entry.id} to draft",
        request=request,
    )
    db.commit()
    db.refresh(entry)
    return entry


@router.post("/journal-entries/{entry_id}/approve", response_model=JournalEntryResponse)
def approve_journal_entry(
    entry_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer")),
):
    """Approve a posted journal entry."""
    entry = _get_entry_or_404(db, entry_id)
    if entry.status != "posted":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Can only approve a posted entry; current status is '{entry.status}'",
        )
    if entry.prepared_by_user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot approve an entry you prepared (segregation of duties)",
        )

    entry.status = "approved"
    entry.reviewed_by_user_id = current_user.id
    db.flush()
    locking.bump(entry)
    audit_svc.record(
        db,
        user=current_user,
        action="approve",
        resource_type="journal_entry",
        resource_id=entry.id,
        new={"status": "approved", "reviewed_by_user_id": current_user.id},
        summary=f"approved journal entry {entry.reference or entry.id}",
        request=request,
    )
    db.commit()
    db.refresh(entry)
    return entry
