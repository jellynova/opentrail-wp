from typing import List
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File, status
from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_active_user, require_role
from app.models.trial_balance import TrialBalanceEntry
from app.models.user import User
from app.schemas.trial_balance import (
    TrialBalanceEntryResponse,
    TrialBalanceEntryUpdate,
    WorkingTrialBalanceRow,
    ConnectorImportRequest,
    ImportResult,
)
from app.models.period import FiscalYear, Period
from app.services import audit as audit_svc
from app.services import locking
from app.services import trial_balance as tb_svc

router = APIRouter()


def ensure_period_editable(db: Session, period_id: int) -> Period:
    """Closed periods (and closed/locked years) are frozen: reopen before changing figures."""
    period = db.get(Period, period_id)
    if period is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Period not found")
    fy = db.get(FiscalYear, period.fiscal_year_id)
    if period.is_closed or (fy is not None and fy.status in ("closed", "locked")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Period '{period.name}' is closed; reopen it before changing its trial balance",
        )
    return period


@router.get("/trial-balance", response_model=List[TrialBalanceEntryResponse])
def get_trial_balance(
    period_id: int = Query(..., description="Period ID to retrieve trial balance for"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Return raw trial balance entries for a given period."""
    entries = db.scalars(
        select(TrialBalanceEntry).where(TrialBalanceEntry.period_id == period_id)
    ).all()
    return entries


@router.post("/trial-balance/import/csv", response_model=ImportResult)
async def import_csv(
    request: Request,
    period_id: int = Query(...),
    fiscal_year_id: int = Query(...),
    acct_fmtd_col: str = Query("Account", description="CSV column name for account identifier"),
    period_debit_col: str = Query("Debit", description="CSV column name for period debit"),
    period_credit_col: str = Query("Credit", description="CSV column name for period credit"),
    opening_debit_col: str = Query("Opening Debit", description="CSV column name for opening debit"),
    opening_credit_col: str = Query("Opening Credit", description="CSV column name for opening credit"),
    ytd_debit_col: str = Query("YTD Debit", description="CSV column name for YTD debit"),
    ytd_credit_col: str = Query("YTD Credit", description="CSV column name for YTD credit"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer")),
):
    """Import trial balance from a CSV file upload."""
    column_mapping = {
        acct_fmtd_col: "acct_fmtd",
        period_debit_col: "period_debit",
        period_credit_col: "period_credit",
        opening_debit_col: "opening_debit",
        opening_credit_col: "opening_credit",
        ytd_debit_col: "ytd_debit",
        ytd_credit_col: "ytd_credit",
    }

    ensure_period_editable(db, period_id)
    content = await file.read()
    imported, updated, errors = tb_svc.import_from_csv(
        db=db,
        period_id=period_id,
        file_content=content,
        column_mapping=column_mapping,
        fiscal_year_id=fiscal_year_id,
    )
    audit_svc.record(
        db,
        user=current_user,
        action="import",
        resource_type="trial_balance",
        resource_id=period_id,
        new={"source": "csv", "imported": imported, "updated": updated, "errors": len(errors)},
        summary=f"imported a trial balance from CSV ({imported} new, {updated} updated)",
        request=request,
        commit=True,
    )
    return ImportResult(records_imported=imported, records_updated=updated, errors=errors)


@router.post("/trial-balance/import/connector", response_model=ImportResult)
def import_from_connector(
    data: ConnectorImportRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer")),
):
    """Pull trial balance from an external connector and upsert entries."""
    ensure_period_editable(db, data.period_id)
    imported, updated, errors = tb_svc.import_from_connector(
        db=db,
        connector_id=data.connector_id,
        fiscal_year_id=data.fiscal_year_id,
        period_id=data.period_id,
        fiscal_year=data.fiscal_year,
        period_number=data.period_number,
    )
    audit_svc.record(
        db,
        user=current_user,
        action="import",
        resource_type="trial_balance",
        resource_id=data.period_id,
        new={
            "source": "connector",
            "connector_id": data.connector_id,
            "imported": imported,
            "updated": updated,
            "errors": len(errors),
        },
        summary=f"pulled a trial balance from connector #{data.connector_id} ({imported} new, {updated} updated)",
        request=request,
        commit=True,
    )
    return ImportResult(records_imported=imported, records_updated=updated, errors=errors)


@router.put("/trial-balance/{entry_id}", response_model=TrialBalanceEntryResponse)
def update_entry(
    entry_id: int,
    data: TrialBalanceEntryUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer")),
):
    """
    Manually adjust a trial balance entry.

    Closed periods are frozen: reopen the period first if the figures really must change.
    A stale ``version`` is rejected with 409 (PLAN §8.1).
    """
    entry = db.get(TrialBalanceEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trial balance entry not found")

    try:
        locking.check_version(entry, data.version, "trial balance entry")
    except locking.VersionConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
            headers={"X-Conflict-Reason": "stale-version"},
        )

    ensure_period_editable(db, entry.period_id)

    payload = data.model_dump(exclude_unset=True, exclude={"version"})
    before = audit_svc.snapshot(entry, list(payload))
    for field, value in payload.items():
        setattr(entry, field, value)
    entry.source = "manual"
    entry.updated_at = datetime.now(timezone.utc)
    db.flush()
    locking.bump(entry)

    audit_svc.record(
        db,
        user=current_user,
        action="update",
        resource_type="trial_balance_entry",
        resource_id=entry.id,
        old=before,
        new=audit_svc.snapshot(entry, list(payload)),
        summary=f"adjusted trial balance entry #{entry.id}",
        request=request,
    )
    db.commit()
    db.refresh(entry)
    return entry


@router.get("/trial-balance/working", response_model=List[WorkingTrialBalanceRow])
def get_working_trial_balance(
    period_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Return the working trial balance including journal entry adjustments."""
    rows = tb_svc.get_working_trial_balance(db=db, period_id=period_id)
    return rows
