from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
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
from app.services import trial_balance as tb_svc

router = APIRouter()


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

    content = await file.read()
    imported, updated, errors = tb_svc.import_from_csv(
        db=db,
        period_id=period_id,
        file_content=content,
        column_mapping=column_mapping,
        fiscal_year_id=fiscal_year_id,
    )
    return ImportResult(records_imported=imported, records_updated=updated, errors=errors)


@router.post("/trial-balance/import/connector", response_model=ImportResult)
def import_from_connector(
    data: ConnectorImportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer")),
):
    """Pull trial balance from an external connector and upsert entries."""
    imported, updated, errors = tb_svc.import_from_connector(
        db=db,
        connector_id=data.connector_id,
        fiscal_year_id=data.fiscal_year_id,
        period_id=data.period_id,
        fiscal_year=data.fiscal_year,
        period_number=data.period_number,
    )
    return ImportResult(records_imported=imported, records_updated=updated, errors=errors)


@router.put("/trial-balance/{entry_id}", response_model=TrialBalanceEntryResponse)
def update_entry(
    entry_id: int,
    data: TrialBalanceEntryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer")),
):
    """Manually adjust a trial balance entry."""
    entry = db.get(TrialBalanceEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trial balance entry not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(entry, field, value)
    entry.source = "manual"

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
