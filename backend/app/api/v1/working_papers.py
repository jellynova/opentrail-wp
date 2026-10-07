from typing import Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_active_user
from app.models.period import FiscalYear
from app.models.user import User
from app.services import working_papers as wp

router = APIRouter()


@router.get("/working-papers/trial-balance")
def get_working_trial_balance(
    period_id: int = Query(...),
    scheme: Optional[str] = Query(None, description="Mapping scheme name or id to attach classifications"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Working trial balance: opening → unadjusted → AJE → RJE → final per account."""
    try:
        return wp.working_trial_balance(db, period_id, scheme)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get("/working-papers/leadsheets")
def get_leadsheets(
    period_id: int = Query(...),
    scheme: str = Query("PSAB", description="Mapping scheme name or id"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Leadsheets grouped by classification with prior-year comparatives."""
    try:
        return wp.leadsheets(db, period_id, scheme)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get("/working-papers/je-schedule")
def get_je_schedule(
    fiscal_year_id: int = Query(...),
    entry_type: Literal["adjusting", "reclassifying", "elimination", "budget_variance"] = Query("adjusting"),
    include_drafts: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Adjusting (AJE) or reclassification (RJE) journal entry schedule for a fiscal year."""
    if db.get(FiscalYear, fiscal_year_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fiscal year not found")
    return wp.journal_entry_schedule(db, fiscal_year_id, entry_type, include_drafts)
