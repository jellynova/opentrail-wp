from decimal import Decimal
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_active_user, require_role
from app.models.journal_entry import JournalEntry, JournalLine
from app.models.user import User
from app.schemas.journal_entry import (
    JournalEntryCreate,
    JournalEntryUpdate,
    JournalEntryResponse,
)

router = APIRouter()


@router.get("/journal-entries", response_model=List[JournalEntryResponse])
def list_journal_entries(
    period_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    stmt = select(JournalEntry).order_by(JournalEntry.entry_date.desc())
    if period_id is not None:
        stmt = stmt.where(JournalEntry.period_id == period_id)
    return db.scalars(stmt).all()


@router.post("/journal-entries", response_model=JournalEntryResponse, status_code=status.HTTP_201_CREATED)
def create_journal_entry(
    data: JournalEntryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer")),
):
    """Create a journal entry with its lines in draft status."""
    if not data.lines:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Journal entry must have at least one line")

    entry = JournalEntry(
        period_id=data.period_id,
        entry_date=data.entry_date,
        reference=data.reference,
        description=data.description,
        entry_type=data.entry_type,
        prepared_by_user_id=current_user.id,
        status="draft",
    )
    db.add(entry)
    db.flush()  # get entry.id

    for line_data in data.lines:
        line = JournalLine(
            journal_entry_id=entry.id,
            account_id=line_data.account_id,
            debit=line_data.debit,
            credit=line_data.credit,
            description=line_data.description,
            gl_reference=line_data.gl_reference,
        )
        db.add(line)

    db.commit()
    db.refresh(entry)
    return entry


@router.get("/journal-entries/{entry_id}", response_model=JournalEntryResponse)
def get_journal_entry(
    entry_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    entry = db.get(JournalEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Journal entry not found")
    return entry


@router.put("/journal-entries/{entry_id}", response_model=JournalEntryResponse)
def update_journal_entry(
    entry_id: int,
    data: JournalEntryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer")),
):
    """Update a journal entry. Only permitted when status is 'draft'."""
    entry = db.get(JournalEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Journal entry not found")
    if entry.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot edit a journal entry with status '{entry.status}'",
        )

    if data.entry_date is not None:
        entry.entry_date = data.entry_date
    if data.reference is not None:
        entry.reference = data.reference
    if data.description is not None:
        entry.description = data.description
    if data.entry_type is not None:
        entry.entry_type = data.entry_type

    if data.lines is not None:
        # Replace all lines
        for old_line in entry.lines:
            db.delete(old_line)
        db.flush()

        for line_data in data.lines:
            line = JournalLine(
                journal_entry_id=entry.id,
                account_id=line_data.account_id,
                debit=line_data.debit,
                credit=line_data.credit,
                description=line_data.description,
                gl_reference=line_data.gl_reference,
            )
            db.add(line)

    db.commit()
    db.refresh(entry)
    return entry


@router.post("/journal-entries/{entry_id}/post", response_model=JournalEntryResponse)
def post_journal_entry(
    entry_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer")),
):
    """Post a journal entry. Validates that debits == credits before posting."""
    entry = db.get(JournalEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Journal entry not found")
    if entry.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Can only post a draft entry; current status is '{entry.status}'",
        )

    if not entry.lines:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot post an entry with no lines")

    total_debit = sum(Decimal(str(l.debit)) for l in entry.lines)
    total_credit = sum(Decimal(str(l.credit)) for l in entry.lines)

    if total_debit != total_credit:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Journal entry is not balanced: debits={total_debit}, credits={total_credit}",
        )

    entry.status = "posted"
    db.commit()
    db.refresh(entry)
    return entry


@router.post("/journal-entries/{entry_id}/approve", response_model=JournalEntryResponse)
def approve_journal_entry(
    entry_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer")),
):
    """Approve a posted journal entry."""
    entry = db.get(JournalEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Journal entry not found")
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
    db.commit()
    db.refresh(entry)
    return entry
