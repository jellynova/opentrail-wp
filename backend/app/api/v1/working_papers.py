from typing import Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.v1.export_utils import ExportFormat, money_json, tabular_response
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
    format: ExportFormat = Query("json"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Working trial balance: opening → unadjusted → AJE → RJE → final per account."""
    try:
        if format != "json":
            return tabular_response(wp.wtb_table(db, period_id), format, "Working_Trial_Balance")
        return money_json(wp.working_trial_balance(db, period_id, scheme))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get("/working-papers/leadsheets")
def get_leadsheets(
    period_id: int = Query(...),
    scheme: str = Query("PSAB", description="Mapping scheme name or id"),
    format: ExportFormat = Query("json"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Leadsheets grouped by classification with prior-year comparatives."""
    try:
        if format != "json":
            return tabular_response(wp.leadsheets_table(db, period_id, scheme), format, "Leadsheets")
        return money_json(wp.leadsheets(db, period_id, scheme))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get("/working-papers/je-schedule")
def get_je_schedule(
    fiscal_year_id: int = Query(...),
    entry_type: Literal["adjusting", "reclassifying", "elimination", "budget_variance"] = Query("adjusting"),
    include_drafts: bool = Query(False),
    format: ExportFormat = Query("json"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Adjusting (AJE) or reclassification (RJE) journal entry schedule for a fiscal year."""
    if db.get(FiscalYear, fiscal_year_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fiscal year not found")
    if format != "json":
        table = wp.je_schedule_table(db, fiscal_year_id, entry_type, include_drafts)
        return tabular_response(table, format, f"{entry_type}_entries")
    return money_json(wp.journal_entry_schedule(db, fiscal_year_id, entry_type, include_drafts))


@router.get("/working-papers/package")
def get_working_paper_package(
    period_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """ZIP of the working TB, leadsheets, AJE/RJE schedules and PSAB statements (Excel + PDF)."""
    try:
        content = wp.working_paper_package(db, period_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return Response(content=content, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="working_papers_{period_id}.zip"'})
